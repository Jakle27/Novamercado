import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.ensemble import HistGradientBoostingRegressor

from datos_reentrenamiento import leer_observaciones


RAIZ = Path(__file__).resolve().parents[1]
NOMBRE = "novamercado-pronostico"
ALIAS = "vigente"
VENTANA = 7


def leer_csv(nombre):
    with (RAIZ / "data/raw" / nombre).open(
        encoding="utf-8-sig", newline=""
    ) as archivo:
        return list(csv.DictReader(archivo))


def medir(filas, puntos, ajustes, costos):
    error = costo = 0.0
    for fila, punto in zip(filas, puntos, strict=True):
        familia = fila["familia_id"]
        real = int(fila["ventas"])
        esperado = max(0.0, float(punto))
        pedido = max(0, round(esperado + ajustes[familia]))
        faltante, sobrante = costos[familia]
        error += abs(real - esperado)
        costo += faltante * max(real - pedido, 0)
        costo += sobrante * max(pedido - real, 0)
    return {"mae": error / len(filas), "costo": costo}


def ejecutar():
    _, nuevas = leer_observaciones(RAIZ)
    cliente = MlflowClient()
    vigente = cliente.get_model_version_by_alias(NOMBRE, ALIAS)
    version = str(vigente.version)
    fechas = sorted({fila["fecha"] for fila in nuevas})
    if len(fechas) < 2 * VENTANA + 1:
        return {
            "promovido": False,
            "version": version,
            "motivo": f"Hay {len(fechas)} fechas elegibles. Se requieren 15.",
        }

    inicio_calibracion = fechas[-2 * VENTANA]
    inicio_validacion = fechas[-VENTANA]
    config = mlflow.artifacts.load_dict(
        f"runs:/{vigente.run_id}/inferencia/configuracion.json"
    )
    modelo_vigente = mlflow.sklearn.load_model(f"models:/{NOMBRE}/{version}")

    historico = leer_csv("historico_ventas.csv")
    for fila in historico:
        fila["fecha"] = date.fromisoformat(fila["fecha"])

    filas = historico + nuevas
    ventas = {
        (f["fecha"], int(f["tienda_id"]), f["familia_id"]): int(f["ventas"])
        for f in filas
    }
    eventos = defaultdict(set)
    for fila in leer_csv("feriados.csv"):
        eventos[date.fromisoformat(fila["fecha"])].add(
            fila["ambito"].strip().casefold()
        )
    costos = {
        f["familia_id"]: (float(f["costo_faltante"]), float(f["costo_sobrante"]))
        for f in leer_csv("costos.csv")
    }

    def variables(fila):
        dia = fila["fecha"]
        tienda = int(fila["tienda_id"])
        familia = fila["familia_id"]
        ambitos = eventos[dia]
        ciudad = config["ciudades_por_tienda"][str(tienda)]
        return [
            tienda, config["codigos_familia"][familia],
            int(fila["en_promocion"]), dia.weekday(), dia.month, dia.day,
            int("nacional" in ambitos), int(ciudad in ambitos),
            *[
                ventas.get((dia - timedelta(days=n), tienda, familia), np.nan)
                for n in (1, 7, 14, 28)
            ],
        ]

    entrenar = [f for f in filas if f["fecha"] < inicio_calibracion]
    calibrar = [f for f in nuevas if inicio_calibracion <= f["fecha"] < inicio_validacion]
    validar = [f for f in nuevas if f["fecha"] >= inicio_validacion]

    def matriz(registros):
        return np.asarray([variables(f) for f in registros], dtype=float)

    candidato = HistGradientBoostingRegressor(
        loss="absolute_error", max_iter=150, early_stopping=False, random_state=42
    )
    candidato.fit(matriz(entrenar), [int(f["ventas"]) for f in entrenar])

    ajustes_vigente = config["ajustes_por_familia"]
    ajustes = dict(ajustes_vigente)
    residuos = defaultdict(list)
    for fila, punto in zip(calibrar, candidato.predict(matriz(calibrar)), strict=True):
        residuos[fila["familia_id"]].append(
            int(fila["ventas"]) - max(0.0, float(punto))
        )
    for familia, valores in residuos.items():
        faltante, sobrante = costos[familia]
        nivel = faltante / (faltante + sobrante)
        indice = max(0, min(len(valores) - 1, math.ceil(nivel * len(valores)) - 1))
        ajustes[familia] = sorted(valores)[indice]

    x = matriz(validar)
    puntos = candidato.predict(x)
    anterior = medir(validar, modelo_vigente.predict(x), ajustes_vigente, costos)
    nuevo = medir(validar, puntos, ajustes, costos)
    promover = nuevo["costo"] < anterior["costo"] and nuevo["mae"] <= anterior["mae"]

    print(f"Filas de validación: {len(validar)}. Fechas: {inicio_validacion} a {fechas[-1]}.")
    print(f"Vigente {version}: {anterior}")
    print(f"Candidato: {nuevo}")

    mlflow.set_experiment("NovaMercado - reentrenamiento")
    with mlflow.start_run() as run:
        mlflow.log_params({
            "version_comparada": version,
            "inicio_calibracion": inicio_calibracion.isoformat(),
            "inicio_validacion": inicio_validacion.isoformat(),
            "fin_validacion": fechas[-1].isoformat(),
            "filas_entrenamiento": len(entrenar),
            "filas_observadas": len(nuevas),
            "filas_validacion": len(validar),
            "criterio_superado": promover,
        })
        mlflow.log_metrics({
            "mae_vigente": anterior["mae"], "costo_vigente": anterior["costo"],
            "mae_candidato": nuevo["mae"], "costo_candidato": nuevo["costo"],
        })
        mlflow.log_dict(
            {**config, "ajustes_por_familia": ajustes},
            "inferencia/configuracion.json",
        )
        mlflow.sklearn.log_model(
            candidato, artifact_path="modelo",
            signature=infer_signature(x[:1], puntos[:1]),
            pip_requirements=["mlflow==2.22.0", "scikit-learn==1.6.1"],
        )
        run_id = run.info.run_id

    motivo = "El candidato no redujo el costo con un MAE igual o menor."
    if promover:
        registrada = mlflow.register_model(f"runs:/{run_id}/modelo", NOMBRE)
        cliente.set_registered_model_alias(NOMBRE, ALIAS, registrada.version)
        version = str(registrada.version)
        motivo = "El candidato redujo el costo y mantuvo o mejoró el MAE."

    return {"promovido": promover, "version": version, "motivo": motivo}


if __name__ == "__main__":
    print(json.dumps(ejecutar(), ensure_ascii=False))
