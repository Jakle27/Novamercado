CREATE TABLE IF NOT EXISTS solicitudes_prediccion (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recibida_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tienda_id BIGINT NOT NULL,
    fecha DATE NOT NULL,
    version_modelo TEXT NOT NULL,
    solicitud_original JSONB NOT NULL,
    solicitud_validada JSONB NOT NULL,
    respuesta JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS solicitudes_prediccion_tienda_fecha_idx
    ON solicitudes_prediccion (tienda_id, fecha, id);
