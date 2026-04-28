from sqlalchemy import Column, Integer, Float, ForeignKey, DateTime, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class CashRegister(Base):
    __tablename__ = "cash_registers"

    id = Column(Integer, primary_key=True, index=True)
    cajero_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    fondo_inicial = Column(Float, default=0.0)
    total_final = Column(Float)
    estado = Column(String(10), default="abierta")  # abierta, cerrada
    apertura = Column(DateTime(timezone=True), server_default=func.now())
    cierre = Column(DateTime(timezone=True))

    cajero = relationship("User")
