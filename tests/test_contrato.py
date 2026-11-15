import pytest
from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


def enviar_pronostico(tienda_id, promocion):
    return cliente.post(
        "/v1/prediccion",
        json={
            "tienda_id": tienda_id,
            "fecha": "2025-11-17",
            "familias": [
                {"familia_id": "bebidas", "en_promocion": promocion}
            ],
        },
    )


@pytest.fixture
def prediccion_de_prueba(monkeypatch):
    def pronosticar(solicitud):
        assert solicitud.tienda_id == 5
        assert solicitud.familias[0].en_promocion == 8
        return "1", [{
            "familia_id": "bebidas",
            "venta_esperada": 1200.0,
            "cantidad_sugerida": 1300,
        }]

    def guardar(solicitud, datos_originales, respuesta):
        assert respuesta["version_modelo"] == "1"
        return 42

    monkeypatch.delenv("NOVAMERCADO_DATOS", raising=False)
    monkeypatch.setattr("app.main.pronosticar", pronosticar)
    monkeypatch.setattr("app.main.guardar_prediccion", guardar)


def test_pronostico_valido_llega_al_servicio(prediccion_de_prueba):
    respuesta = enviar_pronostico(5, 8)

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["tienda_id"] == 5
    assert datos["fecha"] == "2025-11-17"
    assert datos["version_modelo"] == "1"
    assert datos["id_prediccion"] == 42
    assert datos["predicciones"] == [{
        "familia_id": "bebidas",
        "venta_esperada": 1200.0,
        "cantidad_sugerida": 1300,
    }]
    assert datos["calidad"] == {"estado": "ok", "observaciones": []}


def test_pronostico_repara_y_registra_los_cambios(prediccion_de_prueba):
    respuesta = enviar_pronostico("5", "8")

    assert respuesta.status_code == 200
    calidad = respuesta.json()["calidad"]
    assert calidad["estado"] == "corregido"
    assert [
        (cambio["campo"], cambio["accion"])
        for cambio in calidad["observaciones"]
    ] == [
        ("tienda_id", "reparar"),
        ("familias[0].en_promocion", "reparar"),
    ]


@pytest.mark.parametrize("promocion", ["ocho", -1, 8.5, True])
def test_pronostico_rechaza_promociones_invalidas(promocion):
    respuesta = enviar_pronostico(5, promocion)

    assert respuesta.status_code == 422
    assert any(
        error["campo"] == "familias.0.en_promocion"
        for error in respuesta.json()["detail"]
    )


def test_observaciones_repara_ventas_enviadas_como_texto(monkeypatch):
    def guardar_de_prueba(solicitud, datos_originales, calidad):
        assert solicitud.ventas[0].ventas == 994
        assert datos_originales["ventas"][0]["ventas"] == "994"
        return 1

    monkeypatch.setattr("app.main.guardar_observaciones", guardar_de_prueba)

    respuesta = cliente.post(
        "/v1/observaciones",
        json={
            "tienda_id": 5,
            "fecha": "2025-11-17",
            "ventas": [{"familia_id": "bebidas", "ventas": "994"}],
        },
    )

    assert respuesta.status_code == 200
    resultado = respuesta.json()
    assert resultado["registros_guardados"] == 1
    assert resultado["calidad"]["estado"] == "corregido"
    cambio = resultado["calidad"]["observaciones"][0]
    assert cambio["campo"] == "ventas[0].ventas"
    assert cambio["accion"] == "reparar"
