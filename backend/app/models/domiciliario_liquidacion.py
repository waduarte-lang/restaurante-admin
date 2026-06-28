from sqlalchemy import Column, Integer, Float, String, Date, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class DomiciliarioLiquidacion(Base):
    __tablename__ = "domiciliario_liquidaciones"

    id                  = Column(Integer, primary_key=True, index=True)
    domiciliario_id     = Column(Integer, ForeignKey("domiciliarios.id"), nullable=False)
    fecha               = Column(Date, nullable=False)
    total_efectivo      = Column(Float, default=0.0)       # platos cobrados en efectivo → debe entregar al restaurante
    total_transferencia = Column(Float, default=0.0)       # platos cobrados por transferencia → ya en cuentas
    total_tarjeta       = Column(Float, default=0.0)       # platos cobrados con tarjeta → ya en cuentas
    total_domicilios    = Column(Float, default=0.0)       # suma valor_domicilio del día → restaurante le debe al repartidor
    notas               = Column(Text, nullable=True)
    registrado_por      = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())

    domiciliario = relationship("Domiciliario")
    registrador  = relationship("User")

    __table_args__ = (
        UniqueConstraint("domiciliario_id", "fecha", name="uq_liquidacion_dom_fecha"),
    )
