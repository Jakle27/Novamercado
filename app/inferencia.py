import csv
import os
from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from threading import Lock

import mlflow
import mlflow.sklearn
import psycopg
from mlflow import MlflowClient


NOMBRE = "novamercado-pronostico"
ALIAS = "vigente"
DESFASES = (1, 7, 14, 28)
_bloqueo = Lock()
_cargado = None


class ModeloNoDisponible(RuntimeError):
    pass


def actualizar_modelo():
    global _cargado

    with _bloqueo:
        version = MlflowClient().get_model_version_by_alias(NOMBRE, ALIAS)
        numero = str(version.version)

        if _cargado is not None and _cargado[0] == numero:
            return

        modelo = mlflow.sklearn.load_model(f"models:/{NOMBRE}/{numero}")
        config = mlflow.artifacts.load_dict(
            f"runs:/{version.run_id}/inferencia/configuracion.json"
        )
        _cargado = (numero, modelo, config)


def obtener_modelo():
    actual = _cargado
    if actual is None:
        raise ModeloNoDisponible("Todavía no hay un modelo cargado.")
    return actual


@lru_cache(maxsize=1)
def cargar_historia(carpeta):
    ruta = Path(carpeta)
    with (ruta / "historico_ventas.csv").open(encoding="utf-8-sig", newline="") as archivo:
        ventas = {
            (date.fromisoformat(f["fecha"]), int(f["tienda_id"]), f["familia_id"]):
                int(f["ventas"])
            for f in csv.DictReader(archivo)
        }

    eventos = defaultdict(set)
    with (ruta / "feriados.csv").open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            dia = date.fromisoformat(fila["fecha"])
            eventos[dia].add(fila["ambito"].strip().casefold())

    return ventas, eventos


def pronosticar(solicitud):
    version, modelo, config = obtener_modelo()
    historico, eventos = cargar_historia(os.environ["NOVAMERCADO_DATOS"])

    fecha = solicitud.fecha
    tienda = solicitud.tienda_id
    dias_anteriores = [fecha - timedelta(days=n) for n in DESFASES]
    familias = [fila.familia_id for fila in solicitud.familias]

    with psycopg.connect(connect_timeout=5) as conexion:
        filas = conexion.execute(
            """
            SELECT fecha, familia_id, ventas
            FROM ventas_observadas
            WHERE tienda_id = %s
              AND fecha = ANY(%s)
              AND familia_id = ANY(%s)
            """,
            (tienda, dias_anteriores, familias),
        ).fetchall()
    observadas = {(dia, familia): venta for dia, familia, venta in filas}

    ambitos = eventos.get(fecha, set())
    ciudad = config["ciudades_por_tienda"][str(tienda)]
    variables = []

    for fila in solicitud.familias:
        familia = fila.familia_id
        anteriores = [
            observadas.get(
                (dia, familia),
                historico.get((dia, tienda, familia), float("nan")),
            )
            for dia in dias_anteriores
        ]
        variables.append([
            tienda,
            config["codigos_familia"][familia],
            fila.en_promocion,
            fecha.weekday(),
            fecha.month,
            fecha.day,
            int("nacional" in ambitos),
            int(ciudad in ambitos),
            *anteriores,
        ])

    predicciones = []
    for familia, punto in zip(familias, modelo.predict(variables)):
        esperada = max(0.0, float(punto))
        ajuste = config["ajustes_por_familia"][familia]
        predicciones.append({
            "familia_id": familia,
            "venta_esperada": esperada,
            "cantidad_sugerida": max(0, round(esperada + ajuste)),
        })

    return version, predicciones
