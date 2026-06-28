from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text, Date, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    comanda_numero = Column(Integer, nullable=False, default=1)
    comanda_fecha = Column(Date, server_default=func.current_date())
    tipo = Column(String(10), default="mesa")  # mesa, domicilio
    mesa_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
    mesero_id = Column(Integer, ForeignKey("users.id"))
    estado = Column(String(20), default="abierto")  # abierto, en_cocina, listo, pagado, cancelado
    observaciones = Column(Text)
    total = Column(Float, default=0.0)
    caja_id = Column(Integer, ForeignKey("cash_registers.id"), nullable=True)
    # Campos domicilio
    cliente_nombre = Column(String(150))
    cliente_telefono = Column(String(30))
    cliente_direccion = Column(Text)
    domiciliario_id = Column(Integer, ForeignKey("domiciliarios.id"), nullable=True)
    valor_domicilio = Column(Float, default=0.0, nullable=True)
    metodo_pago = Column(String(30), nullable=True)
    fuente = Column(String(10), default="pos")  # 'pos' | 'manual'
    stock_descontado = Column(Boolean, default=False)  # True cuando ya se descontó inventario
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    mesa = relationship("Table")
    mesero = relationship("User")
    domiciliario = relationship("Domiciliario")
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
    es_adicional = Column(Boolean, default=False)     # true si es de "Otros"

    order = relationship("Order", back_populates="items")
    item = relationship("MenuItem")
