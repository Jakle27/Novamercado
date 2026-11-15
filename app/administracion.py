import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

from app.inferencia import ModeloNoDisponible, obtener_modelo

router = APIRouter(prefix="/admin")
DAG = "/api/v2/dags/reentrenar_novamercado/dagRuns"


def llamar_airflow(ruta, *, token=None, datos=None):
    cuerpo = json.dumps(datos).encode() if datos is not None else None
    headers = {"Accept": "application/json"}
    if cuerpo is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    base = os.environ["AIRFLOW_INTERNO"].rstrip("/")
    with urlopen(Request(base + ruta, data=cuerpo, headers=headers), timeout=8) as respuesta:
        return json.load(respuesta)


def autenticar():
    archivo = Path("/airflow-credenciales/simple_auth_manager_passwords.json.generated")
    credenciales = json.loads(archivo.read_text(encoding="utf-8"))
    respuesta = llamar_airflow(
        "/auth/token", datos={"username": "admin", "password": credenciales["admin"]}
    )
    return respuesta["access_token"]


def version_en_servicio():
    try:
        return obtener_modelo()[0]
    except ModeloNoDisponible:
        raise HTTPException(status_code=503, detail="La API está cargando el modelo vigente.")


@router.post("/reentrenar", status_code=202)
def iniciar():
    try:
        ejecucion = llamar_airflow(
            DAG, token=autenticar(), datos={"logical_date": None, "conf": {}}
        )
        return {"id": ejecucion["dag_run_id"]}
    except (OSError, ValueError, KeyError):
        raise HTTPException(status_code=503, detail="No se pudo iniciar el DAG en Airflow.")


@router.get("/reentrenar/{id}")
def consultar(id: str):
    ruta = f"{DAG}/{quote(id, safe='')}"
    try:
        token = autenticar()
        try:
            ejecucion = llamar_airflow(ruta, token=token)
        except HTTPError as error:
            if error.code == 404:
                raise HTTPException(status_code=404, detail="Ejecución desconocida.")
            raise

        estado = ejecucion["state"]
        if estado == "failed":
            return {
                "estado": "fallido",
                "promovido": False,
                "version": version_en_servicio(),
                "motivo": "Falló la ejecución del DAG. Consulte sus registros en Airflow.",
            }
        if estado != "success":
            return {"estado": "en_curso"}

        resultado = llamar_airflow(
            ruta + "/taskInstances/evaluar_modelos/xcomEntries/return_value",
            token=token,
        )["value"]
        if isinstance(resultado, str):
            resultado = json.loads(resultado)
        return {
            "estado": "exitoso",
            "promovido": resultado["promovido"],
            "version": resultado.get("version") or version_en_servicio(),
            "motivo": resultado["motivo"],
        }
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=503, detail="No se pudo consultar el resultado en Airflow."
        )
