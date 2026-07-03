from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class ListaPrecioProducto(Base):
    __tablename__ = "lista_precio_productos"

    id            = Column(Integer, primary_key=True, index=True)
    codigo        = Column(String(60), index=True)
    descripcion   = Column(String(400), nullable=False)
    precio_unitario = Column(Numeric(18, 2), nullable=False)
    unidad        = Column(String(30), default="UND")
    categoria     = Column(String(100), index=True)
    activo        = Column(Boolean, default=True)
    updated_at    = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Cotizacion(Base):
    __tablename__ = "cotizaciones"

    id               = Column(Integer, primary_key=True, index=True)
    consecutivo      = Column(String(25), unique=True, nullable=False, index=True)
    asesor_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    cliente_nombre   = Column(String(200))
    cliente_nit      = Column(String(30))
    cliente_email    = Column(String(200))
    cliente_telefono = Column(String(30))
    cliente_ciudad   = Column(String(100))
    notas            = Column(Text)
    subtotal         = Column(Numeric(18, 2), default=0)
    iva_pct          = Column(Numeric(5, 2), default=0)
    iva              = Column(Numeric(18, 2), default=0)
    total            = Column(Numeric(18, 2), default=0)
    estado           = Column(String(20), default="borrador")
    created_at       = Column(DateTime, server_default=func.now())

    asesor = relationship("User", foreign_keys=[asesor_id])
    items  = relationship("CotizacionItem", back_populates="cotizacion", cascade="all, delete-orphan")


class CotizacionItem(Base):
    __tablename__ = "cotizacion_items"

    id               = Column(Integer, primary_key=True, index=True)
    cotizacion_id    = Column(Integer, ForeignKey("cotizaciones.id", ondelete="CASCADE"), nullable=False)
    codigo           = Column(String(60))
    descripcion      = Column(String(400))
    unidad           = Column(String(30), default="UND")
    cantidad         = Column(Numeric(10, 2), default=1)
    precio_unitario  = Column(Numeric(18, 2), default=0)
    total            = Column(Numeric(18, 2), default=0)

    cotizacion = relationship("Cotizacion", back_populates="items")
