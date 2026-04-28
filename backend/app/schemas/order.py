from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class OrderItemCreate(BaseModel):
    item_id: int
    cantidad: int = 1
    nota: Optional[str] = None


class OrderItemOut(BaseModel):
    id: int
    item_id: int
    cantidad: int
    precio_unitario: float
    nota: Optional[str]
    estado: str
    item_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    mesa_id: int
    items: List[OrderItemCreate] = []
    observaciones: Optional[str] = None


class OrderUpdate(BaseModel):
    estado: Optional[str] = None
    observaciones: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    mesa_id: int
    mesero_id: Optional[int]
    estado: str
    total: float
    observaciones: Optional[str]
    created_at: datetime
    items: List[OrderItemOut] = []

    class Config:
        from_attributes = True
