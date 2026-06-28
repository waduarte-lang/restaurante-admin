from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CreditoCliente(Base):
    __tablename__ = "credito_clientes"

    id             = Column(Integer, primary_key=True, index=True)
    nombre         = Column(String(200), nullable=False, index=True)
    identificacion = Column(String(50),  nullable=True)   # cédula / NIT
    telefono       = Column(String(30),  nullable=True)
    direccion      = Column(String(500), nullable=True)
    limite_credito = Column(Float, default=0)
    activo         = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    creditos = relationship("Credito", back_populates="cliente", cascade="all, delete-orphan")


class Credito(Base):
    __tablename__ = "creditos"

    id               = Column(Integer, primary_key=True, index=True)
    cliente_id       = Column(Integer, ForeignKey("credito_clientes.id"), nullable=False)
    order_id         = Column(Integer, ForeignKey("orders.id"),           nullable=True)
    monto_total      = Column(Float, nullable=False)
    saldo_pendiente  = Column(Float, nullable=False)
    estado           = Column(String(20), default="pendiente")  # pendiente | parcial | pagado | cancelado
    fecha            = Column(DateTime(timezone=True), server_default=func.now())
    concepto         = Column(String(500), nullable=True)
    cajero_id        = Column(Integer, ForeignKey("users.id"), nullable=True)

    cliente = relationship("CreditoCliente", back_populates="creditos")
    abonos  = relationship("Abono", back_populates="credito", cascade="all, delete-orphan",
                           order_by="Abono.fecha")


class Abono(Base):
    __tablename__ = "abonos"

    id            = Column(Integer, primary_key=True, index=True)
    credito_id    = Column(Integer, ForeignKey("creditos.id"), nullable=False)
    monto         = Column(Float, nullable=False)
    fecha         = Column(DateTime(timezone=True), server_default=func.now())
    metodo_pago   = Column(String(20), default="efectivo")  # efectivo | tarjeta | transferencia
    observaciones = Column(Text, nullable=True)
    cajero_id     = Column(Integer, ForeignKey("users.id"), nullable=True)

    credito = relationship("Credito", back_populates="abonos")
