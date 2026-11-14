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


def test_pronostico_valido_llega_al_servicio():
    respuesta = enviar_pronostico(5, 8)

    assert respuesta.status_code == 503
    assert respuesta.json()["calidad"] == {
        "estado": "ok",
        "observaciones": [],
    }


def test_pronostico_repara_y_registra_los_cambios():
    respuesta = enviar_pronostico("5", "8")

    assert respuesta.status_code == 503
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
