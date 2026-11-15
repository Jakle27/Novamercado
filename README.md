# NovaMercado — Laboratorio 2 de Product Development

Servicio de pronóstico diario de ventas y recomendación de inventario por tienda y familia.

## Instalación desde un clon limpio

1. Abra Docker Desktop y ejecute los comandos desde la raíz del repositorio en Ubuntu con WSL.
2. Coloque `tiendas.csv`, `familias.csv`, `historico_ventas.csv`, `feriados.csv` y `costos.csv`, entregados en el GES, directamente en `data/raw/`.
3. Ejecute `cp -n .env.example .env`. Edite `.env` y sustituya los valores de ejemplo de `POSTGRES_PASSWORD` y `AIRFLOW_DB_PASSWORD` por claves locales. Para la clave de Airflow puede generar un valor hexadecimal con `python3 -c 'import secrets; print(secrets.token_hex(24))'`.
4. Ejecute `docker compose config --quiet` y luego `docker compose up -d --build`.
5. Consulte `http://127.0.0.1:8000/health` hasta que devuelva `{"estado":"ok"}`. Consulte `http://127.0.0.1:8000/modelo` para ver la versión activa. En un registro vacío, el inicializador entrena y registra el primer modelo. Con un alias vigente existente, reutiliza su versión.

API y documentación interactiva en `http://127.0.0.1:8000/docs`, MLflow en `http://127.0.0.1:5000` y Airflow en `http://127.0.0.1:8081`. Airflow genera su propia contraseña para `admin`. Puede consultarse localmente con `docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated`.

## Uso y pruebas

- `POST /v1/prediccion` recibe una tienda, una fecha y las familias con sus promociones.
- `POST /v1/observaciones` registra las ventas reales. Al repetir el mismo contenido, `registros_guardados` devuelve `0`.
- `POST /admin/reentrenar` dispara el DAG y devuelve un identificador con HTTP 202. `GET /admin/reentrenar/{id}` consulta su estado. Con cero ventas nuevas aptas, el DAG termina correctamente y conserva la versión vigente.
- Las pruebas de contrato se ejecutan con el comando siguiente. Sustituyen las dependencias que intervienen en el pronóstico y su persistencia.

```bash
docker compose run --rm --no-deps \
  -e NOVAMERCADO_DATOS= \
  -v "$PWD/tests:/app/tests:ro" \
  -v "$PWD/requirements-dev.txt:/app/requirements-dev.txt:ro" \
  api sh -c 'python -m pip install -q -r requirements-dev.txt &&
    python -m pytest -q -p no:cacheprovider'
```

`docker compose stop` detiene los servicios y conserva sus volúmenes. El comando `docker compose down -v` borra los datos persistentes del proyecto al que se aplica.

La carpeta `evidencias/` contiene la comparación de modelos, el arranque integrado, la recarga de la API y el reentrenamiento de principio a fin con ventas simuladas.
