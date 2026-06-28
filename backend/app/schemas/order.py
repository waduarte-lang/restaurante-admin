from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date


class OrderItemCreate(BaseModel):
    item_id: int
    cantidad: int = 1
    nota: Optional[str] = None
    precio_unitario: Optional[float] = None  # si se envía, sobreescribe el precio del menú


class OtroItemCreate(BaseModel):
    menu_item_id: int  # proteína, jugo o ensalada del menú del día
    cantidad: int = 1
    precio_unitario: float  # precio manual


class OrderItemOut(BaseModel):
    id: int
    item_id: int
    cantidad: int
    precio_unitario: float
    nota: Optional[str]
    estado: str
    item_nombre: Optional[str] = None
    es_adicional: bool = False

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    tipo: str = "mesa"
    mesa_id: Optional[int] = None
    items: List[OrderItemCreate] = []
    observaciones: Optional[str] = None
    metodo_pago: Optional[str] = None
    monto_efectivo: Optional[float] = None  # monto del primer método en pago mixto
    mixto_metodo1: Optional[str] = None     # primer método (default 'efectivo')
    mixto_metodo2: Optional[str] = None     # segundo método (default 'transferencia')
    estado: Optional[str] = None          # si se envía 'pagado', la comanda nace pagada
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None
    domiciliario_id: Optional[int] = None
    valor_domicilio: Optional[float] = 0.0


class OtrosOrderCreate(BaseModel):
    tipo: str = "mesa"
    mesa_id: Optional[int] = None
    items: List[OtroItemCreate] = []
    observaciones: Optional[str] = None
    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    cliente_direccion: Optional[str] = None


class OrderUpdate(BaseModel):
    estado: Optional[str] = None
    observaciones: Optional[str] = None
    metodo_pago: Optional[str] = None
    domiciliario_id: Optional[int] = None
    valor_domicilio: Optional[float] = None
    mesa_id: Optional[int] = None
    comanda_fecha: Optional[str] = None
    total: Optional[float] = None


class OrderOut(BaseModel):
    id: int
    comanda_numero: int
    comanda_fecha: Optional[date]
    tipo: str
    mesa_id: Optional[int]
    mesero_id: Optional[int]
    estado: str
    total: float
    observaciones: Optional[str]
    cliente_nombre: Optional[str]
    cliente_telefono: Optional[str]
    cliente_direccion: Optional[str]
    domiciliario_id: Optional[int] = None
    valor_domicilio: Optional[float] = None
    metodo_pago: Optional[str] = None
    fuente: Optional[str] = None
    created_at: datetime
    items: List[OrderItemOut] = []

    class Config:
        from_attributes = True
