from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    unidad = Column(String(20), nullable=False)  # kg, g, L, ml, unidad
    stock_actual = Column(Float, default=0.0)
    stock_minimo = Column(Float, default=0.0)
    costo_unitario = Column(Float, default=0.0)
    proveedor = Column(String(150))
    recetas = relationship("Recipe", back_populates="ingrediente")
    movimientos = relationship("StockMovement", back_populates="ingrediente")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=False)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    cantidad = Column(Float, nullable=False)

    item = relationship("MenuItem", back_populates="recetas")
    ingrediente = relationship("Ingredient", back_populates="recetas")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    ingredient_id = Column(Integer, ForeignKey("ingredients.id"), nullable=False)
    tipo = Column(String(10), nullable=False)  # entrada, salida
    cantidad = Column(Float, nullable=False)
    motivo = Column(String(200))
    usuario_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ingrediente = relationship("Ingredient", back_populates="movimientos")
    usuario = relationship("User")
