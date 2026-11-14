import runpy
from collections import defaultdict

import mlflow
import mlflow.sklearn
from mlflow import MlflowClient
from mlflow.models import infer_signature

NOMBRE = "novamercado-pronostico"
ALIAS = "vigente"

evaluacion = runpy.run_path("scripts/evaluar_modelos.py")
modelo = evaluacion["modelo"]
calibracion = evaluacion["calibracion"]
prueba = evaluacion["evaluacion"]
costos = evaluacion["costos"]
cuantil = evaluacion["cuantil"]

residuos = defaultdict(list)
for fila, punto in zip(calibracion, modelo.predict([f[4] for f in calibracion])):
    _, familia, real, _, _ = fila
    residuos[familia].append(real - max(0, float(punto)))

ajustes = {}
for familia, (faltante, sobrante) in costos.items():
    nivel = faltante / (faltante + sobrante)
    ajustes[familia] = cuantil(residuos[familia], nivel)

error = costo = 0.0
for fila, punto in zip(prueba, modelo.predict([f[4] for f in prueba])):
    _, familia, real, _, _ = fila
    esperado = max(0, float(punto))
    sugerido = max(0, round(esperado + ajustes[familia]))
    faltante, sobrante = costos[familia]
    error += abs(real - esperado)
    costo += faltante * max(real - sugerido, 0)
    costo += sobrante * max(sugerido - real, 0)

configuracion = {
    "variables": [
        "tienda_id", "familia_codigo", "en_promocion",
        "dia_semana", "mes", "dia_mes",
        "feriado_nacional", "feriado_local",
        "ventas_lag_1", "ventas_lag_7", "ventas_lag_14", "ventas_lag_28",
    ],
    "codigos_familia": evaluacion["familias"],
    "ciudades_por_tienda": {
        str(tienda): ciudad for tienda, ciudad in evaluacion["tiendas"].items()
    },
    "ajustes_por_familia": ajustes,
}

mlflow.set_experiment("NovaMercado - evaluación inicial")
with mlflow.start_run(run_name="HistGradientBoosting - febrero 2026") as run:
    mlflow.log_params({
        "modelo": "HistGradientBoostingRegressor",
        "inicio_calibracion": str(evaluacion["INICIO_CALIBRACION"]),
        "inicio_evaluacion": str(evaluacion["INICIO_EVALUACION"]),
        "filas_evaluacion": len(prueba),
        "semilla": 42,
    })
    mlflow.log_metrics({"mae": error / len(prueba), "costo_total": costo})
    mlflow.log_dict(configuracion, "inferencia/configuracion.json")
    ejemplo = modelo.predict([prueba[0][4]])
    import numpy as np
    entrada = np.asarray([prueba[0][4]], dtype=float)
    mlflow.sklearn.log_model(
        modelo,
        artifact_path="modelo",
        signature=infer_signature(entrada, ejemplo),
        pip_requirements=["mlflow==2.22.0", "scikit-learn==1.6.1"],
    )
    run_id = run.info.run_id

version = mlflow.register_model(f"runs:/{run_id}/modelo", NOMBRE)
cliente = MlflowClient()
cliente.set_registered_model_alias(NOMBRE, ALIAS, version.version)
vigente = cliente.get_model_version_by_alias(NOMBRE, ALIAS)

print(f"Modelo registrado: {vigente.name}")
print(f"Alias: {ALIAS}")
print(f"Versión: {vigente.version}")
print(f"MAE: {error / len(prueba):,.2f}")
print(f"Costo total: {costo:,.2f}")
