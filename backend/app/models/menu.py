from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class MenuCategory(Base):
    __tablename__ = "menu_categories"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    orden = Column(Integer, default=0)
    items = relationship("MenuItem", back_populates="categoria")


class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(String(300))
    precio = Column(Float, nullable=False)
    categoria_id = Column(Integer, ForeignKey("menu_categories.id"))
    activo = Column(Boolean, default=True)
    categoria = relationship("MenuCategory", back_populates="items")
    recetas = relationship("Recipe", back_populates="item")
