from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CreditoClienteCreate(BaseModel):
    nombre:         str
    identificacion: Optional[str]   = None
    telefono:       Optional[str]   = None
    direccion:      Optional[str]   = None
    limite_credito: float           = 0


class CreditoClienteUpdate(BaseModel):
    nombre:         Optional[str]   = None
    identificacion: Optional[str]   = None
    telefono:       Optional[str]   = None
    direccion:      Optional[str]   = None
    limite_credito: Optional[float] = None
    activo:         Optional[bool]  = None


class CreditoClienteOut(BaseModel):
    id:             int
    nombre:         str
    identificacion: Optional[str]  = None
    telefono:       Optional[str]  = None
    direccion:      Optional[str]  = None
    limite_credito: float          = 0
    activo:         bool
    total_deuda:    float          = 0   # campo calculado, no en DB

    class Config:
        from_attributes = True


# ─── Abonos ─────────────────────────────────────────────────────────────────

class AbonoCreate(BaseModel):
    monto:         float
    metodo_pago:   str            = "efectivo"
    observaciones: Optional[str] = None


class AbonoOut(BaseModel):
    id:            int
    monto:         float
    fecha:         datetime
    metodo_pago:   str
    observaciones: Optional[str] = None

    class Config:
        from_attributes = True


# ─── Créditos ────────────────────────────────────────────────────────────────

class CreditoCreate(BaseModel):
    cliente_id:  int
    order_id:    Optional[int]  = None
    monto_total: float
    concepto:    Optional[str] = None


class CreditoOut(BaseModel):
    id:              int
    cliente_id:      int
    cliente_nombre:  str          = ""
    order_id:        Optional[int] = None
    monto_total:     float
    saldo_pendiente: float
    estado:          str
    fecha:           datetime
    concepto:        Optional[str] = None
    abonos:          List[AbonoOut] = []

    class Config:
        from_attributes = True
