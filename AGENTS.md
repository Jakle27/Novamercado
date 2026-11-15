# Contexto del proyecto NovaMercado

Este repositorio contiene el Laboratorio 2 de Product Development.
El contrato de la API está definido en el enunciado. Las pruebas de
contrato deben poder ejecutarse sin un servidor de MLflow.

Use rutas relativas al repositorio. Los CSV oficiales se colocan en
data/raw/ y las credenciales locales en .env. Mantenga ambos fuera de Git.

Para cada pronóstico use únicamente ventas anteriores a la fecha solicitada.
Mantenga la idempotencia de las observaciones y evalúe el candidato y el
vigente sobre las mismas filas antes de cambiar el alias en MLflow.

Consulte README.md para la instalación y DECISIONES.md para las reglas
de validación, modelado y promoción.
