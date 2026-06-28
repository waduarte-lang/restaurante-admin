from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class OrderEstadoLog(Base):
    """Registra cada transición de estado de una orden para análisis de tiempos."""
    __tablename__ = "order_estado_logs"

    id             = Column(Integer, primary_key=True)
    order_id       = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    tipo_orden     = Column(String(15), nullable=True)    # mesa | domicilio
    estado_de      = Column(String(20), nullable=True)    # null = estado inicial al crear
    estado_a       = Column(String(20), nullable=False)
    usuario_id     = Column(Integer, ForeignKey("users.id"), nullable=True)
    usuario_nombre = Column(String(100), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())

    order   = relationship("Order",  foreign_keys=[order_id])
    usuario = relationship("User",   foreign_keys=[usuario_id])
