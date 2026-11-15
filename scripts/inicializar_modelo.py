import os
import runpy
import time
from urllib.error import URLError
from urllib.request import urlopen

from mlflow import MlflowClient
from mlflow.exceptions import MlflowException

nombre = "novamercado-pronostico"
alias = "vigente"
url = os.environ["MLFLOW_TRACKING_URI"].rstrip("/")
limite = time.monotonic() + 120

while True:
    try:
        with urlopen(url + "/health", timeout=3) as respuesta:
            if respuesta.status == 200:
                break
    except (OSError, URLError):
        pass
    if time.monotonic() >= limite:
        raise SystemExit("MLflow no estuvo disponible dentro de 120 segundos.")
    time.sleep(2)

cliente = MlflowClient()
try:
    vigente = cliente.get_model_version_by_alias(nombre, alias)
except MlflowException as error:
    alias_ausente = (
        error.error_code == "INVALID_PARAMETER_VALUE"
        and f"Registered model alias {alias} not found" in str(error)
    )
    if error.error_code != "RESOURCE_DOES_NOT_EXIST" and not alias_ausente:
        raise
    print("Registro inicial: se entrenará y publicará el primer modelo.")
    runpy.run_path("scripts/registrar_modelo.py", run_name="__main__")
else:
    print(f"Modelo vigente {vigente.version} disponible. Se reutiliza el registro.")
