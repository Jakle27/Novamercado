# Decisiones técnicas de NovaMercado

## Pronóstico y pedido

La referencia semanal utiliza la venta del mismo día de la semana anterior. HistGradientBoosting usa la promoción de la solicitud, calendario, feriados nacionales y locales, y ventas de 1, 7, 14 y 28 días antes. Los desfases se consultan por fecha exacta y las ausencias se conservan como valores faltantes. El pronóstico consulta únicamente ventas de fechas anteriores a la solicitada.

El ajuste de la cantidad sugerida se calcula por familia con los residuos de calibración y el cuantil costo_faltante / (costo_faltante + costo_sobrante). El pedido final se redondea y se limita a cantidades no negativas. En la evaluación temporal de febrero, el candidato obtuvo MAE 39.92 y costo 101,591.00. La referencia obtuvo MAE 59.43 y costo 143,625.60.

## Validación y persistencia

La API registra reparaciones de formatos reconocibles, como identificadores con prefijo, fechas alternativas admitidas, nombres de familias del catálogo y números enviados como texto. Reporta una advertencia si se solicita un subconjunto de familias y pronostica las recibidas. Rechaza con HTTP 422 las ventas negativas, las familias duplicadas y otros valores ambiguos o inválidos. La venta real se identifica por tienda, fecha y familia. PostgreSQL conserva las solicitudes válidas, los pronósticos con su versión y las observaciones.

## Reentrenamiento y operación

El DAG vincula las ventas posteriores al histórico con la primera solicitud de pronóstico que incluyó la misma tienda, fecha y familia. De esa solicitud recupera la promoción. Con al menos 15 fechas elegibles, reserva las últimas siete para validación y las siete anteriores para calibración. Entrena con el histórico y las observaciones anteriores. Si faltan datos de calibración para una familia, conserva su ajuste vigente.

El candidato se promueve si reduce el costo total y obtiene un MAE igual o menor sobre las mismas filas de validación. MLflow conserva las métricas y el modelo. La API consulta el alias vigente periódicamente y conserva el modelo cargado durante una interrupción temporal de MLflow. PostgreSQL del producto y PostgreSQL de Airflow usan volúmenes independientes. Los CSV oficiales se montan desde una ruta relativa y las credenciales se configuran localmente.
