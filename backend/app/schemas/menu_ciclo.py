from pydantic import BaseModel
from typing import Optional, List


class MenuCicloIn(BaseModel):
    ciclo: int
    dia_semana: int
    sopa_id: Optional[int] = None
    proteina_id: Optional[int] = None
    ensalada_id: Optional[int] = None
    especial_id: Optional[int] = None
    contorno: Optional[str] = None


class MenuCicloOut(MenuCicloIn):
    id: int
    sopa_nombre: Optional[str] = None
    proteina_nombre: Optional[str] = None
    ensalada_nombre: Optional[str] = None
    especial_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class MenuCicloBulkIn(BaseModel):
    ciclo: int
    dias: List[MenuCicloIn]


class MenuCicloConfigOut(BaseModel):
    id: int
    ciclo_activo: int

    class Config:
        from_attributes = True


class MenuCicloConfigIn(BaseModel):
    ciclo_activo: int
