import psycopg
from psycopg.types.json import Jsonb

from app.schemas import SolicitudObservaciones


def guardar_observaciones(
    solicitud: SolicitudObservaciones, datos_originales: dict, calidad: dict
) -> int:
    guardados = 0
    # Una sola transacción para las ventas y el registro de la solicitud.
    with psycopg.connect(connect_timeout=5) as conexion:
        with conexion.cursor() as cursor:
            for fila in solicitud.ventas:
                cursor.execute(
                    """
                    INSERT INTO ventas_observadas (tienda_id, fecha, familia_id, ventas)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tienda_id, fecha, familia_id) DO UPDATE
                    SET ventas = EXCLUDED.ventas
                    WHERE ventas_observadas.ventas IS DISTINCT FROM EXCLUDED.ventas
                    RETURNING familia_id
                    """,
                    (solicitud.tienda_id, solicitud.fecha, fila.familia_id, fila.ventas),
                )
                guardados += int(cursor.fetchone() is not None)

            cursor.execute(
                """
                INSERT INTO solicitudes_observaciones
                    (solicitud, calidad, registros_guardados)
                VALUES (%s, %s, %s)
                """,
                (Jsonb(datos_originales), Jsonb(calidad), guardados),
            )
    return guardados


def guardar_prediccion(solicitud, datos_originales, respuesta):
    with psycopg.connect(connect_timeout=5) as conexion:
        fila = conexion.execute(
            """
            INSERT INTO solicitudes_prediccion
                (tienda_id, fecha, version_modelo, solicitud_original,
                 solicitud_validada, respuesta)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                solicitud.tienda_id,
                solicitud.fecha,
                respuesta["version_modelo"],
                Jsonb(datos_originales),
                Jsonb(solicitud.model_dump(mode="json")),
                Jsonb(respuesta),
            ),
        ).fetchone()
    return fila[0]
