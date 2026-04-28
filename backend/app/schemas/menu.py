from pydantic import BaseModel
from typing import Optional, List


class CategoryCreate(BaseModel):
    nombre: str
    orden: int = 0


class CategoryOut(BaseModel):
    id: int
    nombre: str
    orden: int

    class Config:
        from_attributes = True


class MenuItemCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    precio: float
    categoria_id: Optional[int] = None


class MenuItemUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    precio: Optional[float] = None
    categoria_id: Optional[int] = None
    activo: Optional[bool] = None


class MenuItemOut(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    precio: float
    categoria_id: Optional[int]
    activo: bool

    class Config:
        from_attributes = True
