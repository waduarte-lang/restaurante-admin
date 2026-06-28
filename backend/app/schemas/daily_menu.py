from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class DailyMenuItemIn(BaseModel):
    tipo: str  # sopa, carne, ensalada, contorno
    menu_item_id: Optional[int] = None
    contorno_nombre: Optional[str] = None


class DailyMenuItemOut(BaseModel):
    id: int
    tipo: str
    menu_item_id: Optional[int]
    contorno_nombre: Optional[str]
    nombre: Optional[str] = None  # nombre del plato

    class Config:
        from_attributes = True


class DailyMenuCreate(BaseModel):
    fecha: date
    precio: float = 0.0
    precio_sopa: float = 8000.0
    precio_proteina: float = 10000.0
    items: List[DailyMenuItemIn]


class DailyMenuOut(BaseModel):
    id: int
    fecha: date
    activo: bool
    precio: float = 0.0
    precio_sopa: float = 8000.0
    precio_proteina: float = 10000.0
    items: List[DailyMenuItemOut] = []

    class Config:
        from_attributes = True
