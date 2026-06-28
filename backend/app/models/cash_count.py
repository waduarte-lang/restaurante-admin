from sqlalchemy import Column, Integer, Float, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CashCount(Base):
    __tablename__ = "cash_counts"

    id = Column(Integer, primary_key=True, index=True)
    caja_id = Column(Integer, ForeignKey("cash_registers.id"), nullable=False)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Denominaciones en JSON: {"100000": 3, "50000": 5, ...}
    denominaciones = Column(Text, nullable=False, default="{}")

    # Totales calculados
    total_contado = Column(Float, nullable=False, default=0.0)
    total_esperado = Column(Float, nullable=False, default=0.0)
    diferencia = Column(Float, nullable=False, default=0.0)  # contado - esperado

    observaciones = Column(String(400))

    caja = relationship("CashRegister")
    usuario = relationship("User")
