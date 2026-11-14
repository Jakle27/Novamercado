SELECT
    v.fecha,
    v.tienda_id,
    v.familia_id,
    v.ventas,
    p.en_promocion
FROM ventas_observadas AS v
JOIN LATERAL (
    SELECT (f->>'en_promocion')::bigint AS en_promocion
    FROM solicitudes_prediccion AS s
    CROSS JOIN LATERAL
        jsonb_array_elements(s.solicitud_validada->'familias') AS f
    WHERE s.tienda_id = v.tienda_id
      AND s.fecha = v.fecha
      AND f->>'familia_id' = v.familia_id
    ORDER BY s.id ASC
    LIMIT 1
) AS p ON TRUE
WHERE v.fecha > :'fin_historico'::date
ORDER BY v.fecha, v.tienda_id, v.familia_id;
