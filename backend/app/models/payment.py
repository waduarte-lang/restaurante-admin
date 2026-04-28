from sqlalchemy import Column, Integer, Float, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    monto = Column(Float, nullable=False)
    metodo = Column(String(30), default="efectivo")  # efectivo, tarjeta, transferencia
    cajero_id = Column(Integer, ForeignKey("users.id"))
    caja_id = Column(Integer, ForeignKey("cash_registers.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    order = relationship("Order", back_populates="pagos")
    cajero = relationship("User")
