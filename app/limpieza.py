import csv
import re
import unicodedata
from copy import deepcopy
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path


class EntradaInvalida(ValueError):
    pass


def clave(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


@lru_cache(maxsize=4)
def cargar_catalogos(carpeta):
    ruta = Path(carpeta)
    with (ruta / "tiendas.csv").open(encoding="utf-8-sig", newline="") as archivo:
        tiendas = {int(fila["tienda_id"]) for fila in csv.DictReader(archivo)}

    familias = set()
    alias = {}
    with (ruta / "familias.csv").open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            identificador = fila["familia_id"]
            familias.add(identificador)
            for nombre in (identificador, fila["nombre"]):
                alias.setdefault(clave(nombre), set()).add(identificador)

    if not tiendas or not familias:
        raise ValueError("Los catálogos deben contener tiendas y familias.")
    return tiendas, familias, alias


def entero(valor, *, tienda=False, ventas=False):
    if isinstance(valor, float) and valor.is_integer() and abs(valor) <= 2**53 - 1:
        return int(valor)
    if not isinstance(valor, str):
        return valor

    texto = valor.strip()
    if tienda and re.fullmatch(r"[Tt][0-9]{1,18}", texto):
        return int(texto[1:])
    if re.fullmatch(r"[0-9]{1,18}", texto):
        return int(texto)
    if ventas:
        if re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3}){1,5}", texto):
            return int(texto.replace(",", ""))
        if re.fullmatch(r"[0-9]{1,18},0", texto):
            return int(texto.split(",")[0])
    return valor


def fecha_iso(valor):
    if not isinstance(valor, str):
        return valor
    if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", valor):
        try:
            return datetime.strptime(valor, "%d/%m/%Y").date().isoformat()
        except ValueError:
            return valor
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T00:00:00", valor):
        try:
            return date.fromisoformat(valor[:10]).isoformat()
        except ValueError:
            return valor
    return valor


def limpiar_solicitud(datos, lista, campo_numerico, catalogos=None):
    limpio = deepcopy(datos)
    cambios = []

    def cambiar(registro, campo, ruta, nuevo):
        anterior = registro[campo]
        if type(anterior) is not type(nuevo) or anterior != nuevo:
            registro[campo] = nuevo
            cambios.append({
                "campo": ruta,
                "accion": "reparar",
                "detalle": f"{anterior!r} se interpretó como {nuevo!r}",
            })

    if "tienda" in limpio:
        if "tienda_id" in limpio:
            raise EntradaInvalida("Envíe solo tienda_id o su alias tienda.")
        limpio["tienda_id"] = limpio.pop("tienda")
        cambios.append({
            "campo": "tienda_id",
            "accion": "reparar",
            "detalle": "Se reconoció el campo tienda como tienda_id.",
        })

    if "tienda_id" in limpio:
        cambiar(limpio, "tienda_id", "tienda_id", entero(limpio["tienda_id"], tienda=True))
    if "fecha" in limpio:
        cambiar(limpio, "fecha", "fecha", fecha_iso(limpio["fecha"]))

    filas = limpio.get(lista)
    if isinstance(filas, list):
        for indice, fila in enumerate(filas):
            if not isinstance(fila, dict):
                continue
            if campo_numerico in fila:
                cambiar(
                    fila, campo_numerico, f"{lista}[{indice}].{campo_numerico}",
                    entero(fila[campo_numerico], ventas=lista == "ventas"),
                )
            identificador = fila.get("familia_id")
            if catalogos and isinstance(identificador, str):
                _, familias, alias = catalogos
                if identificador not in familias:
                    coincidencias = alias.get(clave(identificador), set())
                    if len(coincidencias) != 1:
                        raise EntradaInvalida(
                            f"{lista}[{indice}].familia_id no identifica una familia del catálogo."
                        )
                    cambiar(
                        fila, "familia_id", f"{lista}[{indice}].familia_id",
                        next(iter(coincidencias)),
                    )

    return limpio, {
        "estado": "corregido" if cambios else "ok",
        "observaciones": cambios,
    }


def revisar_catalogos(solicitud, lista, calidad, catalogos):
    ids = [fila.familia_id for fila in getattr(solicitud, lista)]
    if len(ids) != len(set(ids)):
        raise EntradaInvalida(f"Cada familia debe aparecer una sola vez en {lista}.")

    if catalogos:
        tiendas, familias, _ = catalogos
        if solicitud.tienda_id not in tiendas:
            raise EntradaInvalida("tienda_id no existe en el catálogo.")
        faltantes = sorted(familias - set(ids))
        if lista == "familias" and faltantes:
            calidad["estado"] = "advertencia"
            calidad["observaciones"].append({
                "campo": "familias",
                "accion": "advertir",
                "detalle": "Se procesan solo las familias enviadas. Faltan: " + ", ".join(faltantes),
            })
