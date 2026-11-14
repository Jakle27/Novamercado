CREATE TABLE ventas_observadas (
    tienda_id BIGINT NOT NULL CHECK (tienda_id > 0),
    fecha DATE NOT NULL,
    familia_id TEXT NOT NULL,
    ventas BIGINT NOT NULL CHECK (ventas >= 0),
    PRIMARY KEY (tienda_id, fecha, familia_id)
);

CREATE TABLE solicitudes_observaciones (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recibida_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    solicitud JSONB NOT NULL,
    calidad JSONB NOT NULL,
    registros_guardados INTEGER NOT NULL
);
