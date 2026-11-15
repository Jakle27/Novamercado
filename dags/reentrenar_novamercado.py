import json
import os
import subprocess
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="reentrenar_novamercado",
    start_date=datetime(2026, 3, 1, tz="UTC"),
    schedule=None,
    is_paused_upon_creation=False,
    catchup=False,
    max_active_runs=1,
    tags=["novamercado", "lab2"],
)
def reentrenar_novamercado():
    @task(execution_timeout=timedelta(minutes=8))
    def evaluar_modelos(cantidad_observaciones: int):
        if cantidad_observaciones == 0:
            motivo = "Sin ventas nuevas aptas. Se conserva el modelo vigente."
            print(motivo)
            return {"promovido": False, "motivo": motivo}

        entorno = {
            **os.environ,
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
        }
        resultado = subprocess.run(
            [
                "/home/airflow/entorno-modelo/bin/python",
                "-u",
                "scripts/reentrenar_modelo.py",
            ],
            cwd="/opt/novamercado",
            env=entorno,
            check=True,
            timeout=420,
            stdout=subprocess.PIPE,
            text=True,
        )
        print(resultado.stdout, end="")
        return json.loads(resultado.stdout.splitlines()[-1])


    @task
    def contar_observaciones_nuevas():
        import sys
        from pathlib import Path

        raiz = Path("/opt/novamercado")
        sys.path.insert(0, str(raiz / "scripts"))
        from datos_reentrenamiento import leer_observaciones

        fin, filas = leer_observaciones(raiz)
        cantidad = len(filas)
        print(f"Fin del histórico: {fin}")
        print(f"Ventas nuevas aptas para reentrenamiento: {cantidad}")
        return cantidad

    evaluar_modelos(contar_observaciones_nuevas())


reentrenar_novamercado()
