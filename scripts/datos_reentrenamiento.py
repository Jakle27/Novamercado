import csv
from contextlib import closing
from datetime import date
from pathlib import Path

import psycopg2


def leer_observaciones(raiz):
    raiz = Path(raiz)
    with (raiz / "data/raw/historico_ventas.csv").open(
        encoding="utf-8-sig", newline=""
    ) as archivo:
        fin_historico = max(
            date.fromisoformat(fila["fecha"]) for fila in csv.DictReader(archivo)
        )

    consulta = (raiz / "observaciones.sql").read_text(encoding="utf-8")
    parametro = ":'fin_historico'"
    if consulta.count(parametro) != 1:
        raise ValueError("Se esperaba un parámetro fin_historico en la consulta.")

    with closing(psycopg2.connect(
        connect_timeout=5,
        options="-c statement_timeout=10000",
    )) as conexion:
        conexion.set_session(readonly=True)
        with conexion.cursor() as cursor:
            cursor.execute(consulta.replace(parametro, "%s"), (fin_historico,))
            columnas = [columna.name for columna in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    return fin_historico, filas


if __name__ == "__main__":
    fin_historico, filas = leer_observaciones(Path(__file__).resolve().parents[1])
    print(f"Fin del histórico: {fin_historico}")
    print(f"Filas recuperadas para reentrenamiento: {len(filas)}")
    if filas:
        print(f"Período recuperado: {filas[0]['fecha']} a {filas[-1]['fecha']}")
