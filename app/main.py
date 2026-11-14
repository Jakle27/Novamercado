from urllib.request import urlopen
import logging
from contextlib import asynccontextmanager
from threading import Event, Thread

from app.inferencia import actualizar_modelo

import os

from typing import Annotated

import psycopg

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.limpieza import (
    EntradaInvalida, cargar_catalogos, limpiar_solicitud, revisar_catalogos,
)
from app.inferencia import ALIAS, NOMBRE, ModeloNoDisponible, obtener_modelo, pronosticar
from app.persistencia import guardar_observaciones, guardar_prediccion
from app.schemas import SolicitudObservaciones, SolicitudPronostico

def ciclo_modelo(detener):
    while not detener.is_set():
        try:
            actualizar_modelo()
        except Exception as error:
            logging.getLogger(__name__).warning(
                "No se pudo consultar o cargar el modelo vigente: %s", error
            )
        detener.wait(15)


@asynccontextmanager
async def ciclo_de_vida(app):
    detener = Event()
    hilo = Thread(target=ciclo_modelo, args=(detener,), daemon=True)
    hilo.start()
    try:
        yield
    finally:
        detener.set()


app = FastAPI(title="NovaMercado", lifespan=ciclo_de_vida)


def validar_solicitud(datos, esquema, lista, campo_numerico):
    carpeta = os.environ.get("NOVAMERCADO_DATOS")
    try:
        catalogos = cargar_catalogos(carpeta) if carpeta else None
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Catálogos no disponibles") from error

    try:
        limpio, calidad = limpiar_solicitud(datos, lista, campo_numerico, catalogos)
        solicitud = esquema.model_validate(limpio)
        revisar_catalogos(solicitud, lista, calidad, catalogos)
    except ValidationError as error:
        detalle = [
            {"campo": ".".join(map(str, problema["loc"])), "motivo": problema["msg"]}
            for problema in error.errors()
        ]
        raise HTTPException(status_code=422, detail=detalle) from error
    except EntradaInvalida as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return solicitud, calidad


@app.get("/health")
def health():
    try:
        obtener_modelo()
    except ModeloNoDisponible as error:
        return JSONResponse(
            status_code=503,
            content={"estado": "degradado", "motivo": str(error)},
        )

    motivos = []
    try:
        with psycopg.connect(connect_timeout=3, options="-c statement_timeout=3000") as conexion:
            conexion.execute("SELECT 1").fetchone()
    except psycopg.Error:
        motivos.append("PostgreSQL no está disponible")

    direccion = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
    try:
        with urlopen(f"{direccion.rstrip('/')}/health", timeout=3) as respuesta:
            if respuesta.status != 200:
                motivos.append("MLflow no está disponible")
    except (OSError, ValueError):
        motivos.append("MLflow no está disponible")

    if motivos:
        return {"estado": "degradado", "motivo": ". ".join(motivos)}
    return {"estado": "ok"}


@app.get("/modelo")
def modelo_vigente():
    try:
        version, _, _ = obtener_modelo()
    except ModeloNoDisponible as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"nombre": NOMBRE, "alias": ALIAS, "version": version}


@app.post("/v1/prediccion")
def prediccion(datos: Annotated[dict, Body()]):
    solicitud, calidad = validar_solicitud(
        datos, SolicitudPronostico, "familias", "en_promocion"
    )
    try:
        version, predicciones = pronosticar(solicitud)
    except ModeloNoDisponible as error:
        return JSONResponse(
            status_code=503,
            content={"detail": str(error), "calidad": calidad},
        )
    except psycopg.OperationalError as error:
        raise HTTPException(
            status_code=503, detail="PostgreSQL no está disponible"
        ) from error

    respuesta = {
        "tienda_id": solicitud.tienda_id,
        "fecha": solicitud.fecha.isoformat(),
        "version_modelo": version,
        "predicciones": predicciones,
        "calidad": calidad,
    }

    try:
        respuesta["id_prediccion"] = guardar_prediccion(solicitud, datos, respuesta)
    except psycopg.OperationalError as error:
        raise HTTPException(
            status_code=503, detail="No se pudo guardar la predicción"
        ) from error
    return respuesta


@app.post("/v1/observaciones")
def observaciones(datos: Annotated[dict, Body()]):
    solicitud, calidad = validar_solicitud(
        datos, SolicitudObservaciones, "ventas", "ventas"
    )
    familias = [fila.familia_id for fila in solicitud.ventas]
    if len(familias) != len(set(familias)):
        raise HTTPException(
            status_code=422,
            detail="Cada familia debe aparecer una sola vez en ventas",
        )
    if any(valor > 2**63 - 1 for valor in [solicitud.tienda_id, *(
        fila.ventas for fila in solicitud.ventas
    )]):
        raise HTTPException(status_code=422, detail="El entero excede el límite admitido")

    try:
        guardados = guardar_observaciones(solicitud, datos, calidad)
    except psycopg.OperationalError as error:
        raise HTTPException(status_code=503, detail="PostgreSQL no está disponible") from error

    return {"registros_guardados": guardados, "calidad": calidad}
