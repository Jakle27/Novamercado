import csv
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from sklearn.ensemble import HistGradientBoostingRegressor

DATOS = Path("data/raw")
INICIO_CALIBRACION = date(2026, 1, 4)
INICIO_EVALUACION = date(2026, 2, 1)


def leer(nombre):
    with (DATOS / nombre).open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def normalizar(texto):
    return texto.strip().casefold()


def cuantil(valores, nivel):
    ordenados = sorted(valores)
    indice = max(0, min(len(ordenados) - 1, math.ceil(nivel * len(ordenados)) - 1))
    return ordenados[indice]


tiendas = {
    int(fila["tienda_id"]): normalizar(fila["ciudad"])
    for fila in leer("tiendas.csv")
}
familias = {
    fila["familia_id"]: indice
    for indice, fila in enumerate(leer("familias.csv"))
}
costos = {}
for fila in leer("costos.csv"):
    faltante = float(fila["costo_faltante"])
    sobrante = float(fila["costo_sobrante"])
    if any(not math.isfinite(c) or c < 0 for c in (faltante, sobrante)):
        raise ValueError(f"Costos inválidos para {fila['familia_id']}")
    if faltante + sobrante == 0:
        raise ValueError(f"Ambos costos son cero para {fila['familia_id']}")
    costos[fila["familia_id"]] = faltante, sobrante

eventos = defaultdict(set)
for fila in leer("feriados.csv"):
    eventos[date.fromisoformat(fila["fecha"])].add(normalizar(fila["ambito"]))

historico = sorted(
    (
        date.fromisoformat(fila["fecha"]),
        int(fila["tienda_id"]),
        fila["familia_id"],
        int(fila["ventas"]),
        int(fila["en_promocion"]),
    )
    for fila in leer("historico_ventas.csv")
)

ventas_por_dia = {
    (dia, tienda, familia): ventas
    for dia, tienda, familia, ventas, _ in historico
}
ventas_entrenamiento = defaultdict(list)
for dia, tienda, familia, ventas, _ in historico:
    if dia < INICIO_CALIBRACION:
        ventas_entrenamiento[tienda, familia].append(ventas)

respaldo = {
    clave: median(valores)
    for clave, valores in ventas_entrenamiento.items()
}

filas = []
for dia, tienda, familia, ventas, promocion in historico:
    anteriores = [
        ventas_por_dia.get((dia - timedelta(days=dias), tienda, familia))
        for dias in (1, 7, 14, 28)
    ]
    baseline = anteriores[1]
    if baseline is None:
        baseline = respaldo[tienda, familia]

    ambitos = eventos.get(dia, set())
    variables = [
        tienda, familias[familia], promocion,
        dia.weekday(), dia.month, dia.day,
        int("nacional" in ambitos),
        int(tiendas[tienda] in ambitos),
        *[float("nan") if valor is None else valor for valor in anteriores],
    ]
    filas.append((dia, familia, ventas, baseline, variables))

entrenamiento = [fila for fila in filas if fila[0] < INICIO_CALIBRACION]
calibracion = [
    fila for fila in filas
    if INICIO_CALIBRACION <= fila[0] < INICIO_EVALUACION
]
evaluacion = [fila for fila in filas if fila[0] >= INICIO_EVALUACION]

modelo = HistGradientBoostingRegressor(
    loss="absolute_error",
    max_iter=150,
    early_stopping=False,
    random_state=42,
)
modelo.fit(
    [fila[4] for fila in entrenamiento],
    [fila[2] for fila in entrenamiento],
)


def comparar(nombre, puntos_calibracion, puntos_evaluacion):
    residuos = defaultdict(list)
    for (_, familia, real, _, _), punto in zip(calibracion, puntos_calibracion):
        residuos[familia].append(real - max(0, punto))

    ajustes = {}
    for familia, (faltante, sobrante) in costos.items():
        nivel = faltante / (faltante + sobrante)
        ajustes[familia] = cuantil(residuos[familia], nivel)

    error = costo = 0.0
    for (_, familia, real, _, _), punto in zip(evaluacion, puntos_evaluacion):
        esperado = max(0, punto)
        sugerido = max(0, round(esperado + ajustes[familia]))
        faltante, sobrante = costos[familia]
        error += abs(real - esperado)
        costo += faltante * max(real - sugerido, 0)
        costo += sobrante * max(sugerido - real, 0)

    print(f"{nombre}: MAE={error / len(evaluacion):,.2f} | costo total={costo:,.2f}")


print(f"Filas de entrenamiento: {len(entrenamiento):,}")
print(f"Filas de calibración: {len(calibracion):,}")
print(f"Filas de evaluación: {len(evaluacion):,}")
comparar(
    "Referencia semanal",
    [fila[3] for fila in calibracion],
    [fila[3] for fila in evaluacion],
)
comparar(
    "HistGradientBoosting",
    modelo.predict([fila[4] for fila in calibracion]),
    modelo.predict([fila[4] for fila in evaluacion]),
)
