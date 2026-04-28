from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class IngredientCreate(BaseModel):
    nombre: str
    unidad: str
    stock_actual: float = 0.0
    stock_minimo: float = 0.0
    costo_unitario: float = 0.0
    proveedor: Optional[str] = None


class IngredientUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    stock_minimo: Optional[float] = None
    costo_unitario: Optional[float] = None
    proveedor: Optional[str] = None


class IngredientOut(BaseModel):
    id: int
    nombre: str
    unidad: str
    stock_actual: float
    stock_minimo: float
    costo_unitario: float
    proveedor: Optional[str]
    bajo_stock: bool = False

    class Config:
        from_attributes = True


class StockMovementCreate(BaseModel):
    ingredient_id: int
    tipo: str  # entrada, salida
    cantidad: float
    motivo: Optional[str] = None


class StockMovementOut(BaseModel):
    id: int
    ingredient_id: int
    tipo: str
    cantidad: float
    motivo: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RecipeCreate(BaseModel):
    item_id: int
    ingredient_id: int
    cantidad: float


class RecipeOut(BaseModel):
    id: int
    item_id: int
    ingredient_id: int
    cantidad: float
    ingrediente_nombre: Optional[str] = None
    unidad: Optional[str] = None

    class Config:
        from_attributes = True
