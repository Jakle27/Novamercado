from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, StringConstraints

TiendaId = Annotated[StrictInt, Field(gt=0)]
EnteroNoNegativo = Annotated[StrictInt, Field(ge=0)]
FamiliaId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class FamiliaPronostico(BaseModel):
    familia_id: FamiliaId
    en_promocion: EnteroNoNegativo


class FamiliaObservada(BaseModel):
    familia_id: FamiliaId
    ventas: EnteroNoNegativo


class SolicitudPronostico(BaseModel):
    tienda_id: TiendaId
    fecha: date
    familias: Annotated[list[FamiliaPronostico], Field(min_length=1)]


class SolicitudObservaciones(BaseModel):
    tienda_id: TiendaId
    fecha: date
    ventas: Annotated[list[FamiliaObservada], Field(min_length=1)]
