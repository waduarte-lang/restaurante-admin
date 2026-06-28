from sqlalchemy import Column, Integer, String, Boolean, Date, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class DailyMenu(Base):
    __tablename__ = "daily_menus"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(Date, nullable=False, unique=True)
    activo = Column(Boolean, default=True)
    precio = Column(Float, default=0.0)
    precio_sopa = Column(Float, default=8000.0)
    precio_proteina = Column(Float, default=10000.0)
    creado_por = Column(Integer, ForeignKey("users.id"))

    items = relationship("DailyMenuItem", back_populates="menu", cascade="all, delete-orphan")
    creador = relationship("User")


class DailyMenuItem(Base):
    __tablename__ = "daily_menu_items"

    id = Column(Integer, primary_key=True, index=True)
    daily_menu_id = Column(Integer, ForeignKey("daily_menus.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # sopa, carne, ensalada, contorno
    menu_item_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    contorno_nombre = Column(String(100), nullable=True)  # texto libre para contornos

    menu = relationship("DailyMenu", back_populates="items")
    menu_item = relationship("MenuItem")
