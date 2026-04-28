from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    mesa_id = Column(Integer, ForeignKey("tables.id"), nullable=False)
    mesero_id = Column(Integer, ForeignKey("users.id"))
    estado = Column(String(20), default="abierto")  # abierto, en_cocina, listo, pagado, cancelado
    observaciones = Column(Text)
    total = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    mesa = relationship("Table")
    mesero = relationship("User")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    pagos = relationship("Payment", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    cantidad = Column(Integer, default=1)
    precio_unitario = Column(Float, nullable=False)
    nota = Column(String(200))
    estado = Column(String(20), default="pendiente")  # pendiente, en_preparacion, listo

    order = relationship("Order", back_populates="items")
    item = relationship("MenuItem")
