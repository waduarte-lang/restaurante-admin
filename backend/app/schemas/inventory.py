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
    categoria: Optional[str] = 'Otros'


class IngredientUpdate(BaseModel):
    nombre: Optional[str] = None
    unidad: Optional[str] = None
    stock_actual: Optional[float] = None
    stock_minimo: Optional[float] = None
    costo_unitario: Optional[float] = None
    proveedor: Optional[str] = None
    categoria: Optional[str] = None


class IngredientOut(BaseModel):
    id: int
    nombre: str
    unidad: str
    stock_actual: float
    stock_minimo: float
    costo_unitario: float
    proveedor: Optional[str]
    bajo_stock: bool = False
    categoria: Optional[str] = 'Otros'

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


class RecipeLineIn(BaseModel):
    """Un ingrediente dentro de un bulk-save (sin item_id, va en la ruta)."""
    ingredient_id: int
    cantidad: float
    unidad: Optional[str] = None  # si None, se usa la unidad del ingrediente


class RecipeOut(BaseModel):
    id: int
    item_id: int
    ingredient_id: int
    cantidad: float
    ingrediente_nombre: Optional[str] = None
    unidad: Optional[str] = None

    class Config:
        from_attributes = True


class ShoppingListEntry(BaseModel):
    item_id: int
    porciones: int


class ShoppingListLine(BaseModel):
    ingredient_id: int
    nombre: str
    unidad: str
    necesario: float
    stock_actual: float
    faltante: float
    costo_estimado: float
    categoria: Optional[str] = 'Otros'
