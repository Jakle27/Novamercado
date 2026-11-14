import os
import subprocess
from datetime import timedelta

from airflow.sdk import dag, task
from pendulum import datetime


@dag(
    dag_id="reentrenar_novamercado",
    start_date=datetime(2026, 3, 1, tz="UTC"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["novamercado", "lab2"],
)
def reentrenar_novamercado():
    @task(execution_timeout=timedelta(minutes=8))
    def evaluar_modelos():
        entorno = {
            **os.environ,
            "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2",
        }
        subprocess.run(
            [
                "/home/airflow/entorno-modelo/bin/python",
                "-u",
                "scripts/evaluar_modelos.py",
            ],
            cwd="/opt/novamercado",
            env=entorno,
            check=True,
            timeout=420,
        )

    evaluar_modelos()


reentrenar_novamercado()
