from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date


# ── CRMCliente ────────────────────────────────────────────────────────────────

class CRMClienteBase(BaseModel):
    nombre: str
    nit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None
    direccion: Optional[str] = None
    asesor_id: Optional[int] = None
    activo: bool = True


class CRMClienteCreate(CRMClienteBase):
    pass


class CRMClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    nit: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad: Optional[str] = None
    direccion: Optional[str] = None
    asesor_id: Optional[int] = None
    activo: Optional[bool] = None


class CRMClienteOut(CRMClienteBase):
    id: int
    created_at: datetime
    asesor_nombre: Optional[str] = None

    class Config:
        from_attributes = True


# ── Visita ────────────────────────────────────────────────────────────────────

class VisitaCreate(BaseModel):
    cliente_id: int
    fecha_visita: datetime
    acuerdos: Optional[str] = None
    muestras_entregadas: Optional[str] = None
    proxima_visita: Optional[date] = None


class VisitaUpdate(BaseModel):
    fecha_visita: Optional[datetime] = None
    acuerdos: Optional[str] = None
    muestras_entregadas: Optional[str] = None
    proxima_visita: Optional[date] = None


class VisitaOut(BaseModel):
    id: int
    cliente_id: int
    asesor_id: int
    fecha_visita: datetime
    acuerdos: Optional[str]
    muestras_entregadas: Optional[str]
    proxima_visita: Optional[date]
    created_at: datetime
    cliente_nombre: Optional[str] = None
    asesor_nombre: Optional[str] = None

    class Config:
        from_attributes = True


# ── CalendarioEvento ──────────────────────────────────────────────────────────

class EventoCreate(BaseModel):
    cliente_id: Optional[int] = None
    tipo: str = "pendiente"  # visita | entrega | pendiente
    titulo: str
    descripcion: Optional[str] = None
    fecha_inicio: datetime


class EventoUpdate(BaseModel):
    cliente_id: Optional[int] = None
    tipo: Optional[str] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    completado: Optional[bool] = None


class EventoOut(BaseModel):
    id: int
    cliente_id: Optional[int]
    asesor_id: int
    tipo: str
    titulo: str
    descripcion: Optional[str]
    fecha_inicio: datetime
    completado: bool
    created_at: datetime
    cliente_nombre: Optional[str] = None

    class Config:
        from_attributes = True


# ── Pedido CRM (from DATHA) ───────────────────────────────────────────────────

class PedidoCRMOut(BaseModel):
    id: int
    order_number: Optional[str]
    status: Optional[str]
    customer_name: Optional[str]
    product_name: Optional[str]
    product_sku: Optional[str]
    quantity_to_produce: Optional[int]
    quantity_produced: Optional[int]
    sales_order_number: Optional[str]
    sales_order_delivery_date: Optional[str]
    created_at: Optional[str]
    avance_pct: Optional[float]
    area_name: Optional[str]


# ── Factura / Pago CRM (from DATHA) ──────────────────────────────────────────


# ── Tarea (Planificador + Kanban) ─────────────────────────────────────────────

ETAPAS_VALIDAS = {"prospecto", "contactado", "visita_agendada", "propuesta", "negociacion", "cumplido"}

class TareaCreate(BaseModel):
    titulo: str
    cliente_id: Optional[int] = None
    actividades: Optional[list[str]] = None   # Lista de actividades
    duracion_minutos: int = 60
    que_llevar: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    etapa: str = "prospecto"
    color: str = "#3B82F6"


class TareaUpdate(BaseModel):
    titulo: Optional[str] = None
    cliente_id: Optional[int] = None
    actividades: Optional[list[str]] = None
    duracion_minutos: Optional[int] = None
    que_llevar: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    ejecutado: Optional[bool] = None
    etapa: Optional[str] = None
    color: Optional[str] = None


class TareaOut(BaseModel):
    id: int
    asesor_id: int
    cliente_id: Optional[int]
    titulo: str
    actividades: Optional[list[str]]
    duracion_minutos: int
    que_llevar: Optional[str]
    fecha_inicio: Optional[datetime]
    ejecutado: bool
    etapa: str
    color: str
    created_at: datetime
    cliente_nombre: Optional[str] = None

    class Config:
        from_attributes = True


# ── Factura / Pago CRM (from DATHA) ──────────────────────────────────────────

class FacturaCRMOut(BaseModel):
    id: int
    numero: Optional[str]
    fecha: Optional[str]
    total: Optional[float]
    estado: Optional[str]
    customer_name: Optional[str]
    notas: Optional[str] = None
