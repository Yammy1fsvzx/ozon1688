#!/usr/bin/env python
# -*- coding: utf-8 -*-

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class MatchedProduct(Base):
    """
    Модель для хранения соответствий между товарами Ozon и Alibaba
    """
    __tablename__ = 'matched_products'
    
    id = Column(Integer, primary_key=True)
    ozon_product_id = Column(Integer, ForeignKey('ozon_products.id'), nullable=False)
    alibaba_product_id = Column(Integer, ForeignKey('alibaba_products.id'), nullable=False)
    match_date = Column(DateTime, default=datetime.utcnow)
    relevance_score = Column(Float, nullable=False)
    match_status = Column(String, nullable=False)  # 'found' или 'not_found'
    match_explanation = Column(String)
    
    # Новые поля для веса и габаритов
    weight = Column(Float, nullable=True)  # Вес товара
    dimensions = Column(String, nullable=True)  # Габариты товара в формате "длина x ширина x высота"

    # Связи с другими таблицами
    ozon_product = relationship("OzonProduct", backref="matched_products")
    alibaba_product = relationship("AlibabaProduct", backref="matched_products")

class OzonProduct(Base):
    """
    Модель для хранения товаров Ozon
    """
    __tablename__ = 'ozon_products'
    
    id = Column(Integer, primary_key=True)
    product_id = Column(String, unique=True, nullable=False)
    url = Column(String, nullable=False)
    product_name = Column(String, nullable=False)
    price_current = Column(Integer, nullable=False)
    price_original = Column(Integer)
    images = Column(JSON)  # Список URL изображений
    characteristics = Column(JSON)  # Словарь характеристик
    weight = Column(Float)  # Новое поле для веса
    dimensions = Column(String)  # Новое поле для размеров
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с таблицей задач
    task_id = Column(Integer, ForeignKey('tasks.id'))
    task = relationship("Task", back_populates="product")
    
    def __repr__(self):
        return f"<OzonProduct(id={self.id}, name='{self.product_name}', price={self.price_current}, weight={self.weight}, dimensions='{self.dimensions}')>"

class AlibabaProduct(Base):
    """
    Модель для хранения товаров Alibaba
    """
    __tablename__ = 'alibaba_products'
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    price_usd = Column(Float, nullable=False)
    company_name = Column(String, nullable=False)
    image_url = Column(String)
    sales = Column(Integer)
    shop_years = Column(Integer)
    repurchase_rate = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AlibabaProduct(id={self.id}, title='{self.title}', price={self.price_usd})>"

class ProductProfitability(Base):
    """
    Модель для анализа маржинальности товаров
    """
    __tablename__ = 'product_profitability'
    
    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey('matched_products.id'), nullable=False)
    
    # Информация о товарах
    ozon_name = Column(String, nullable=False)  # Название товара на Ozon
    alibaba_name = Column(String, nullable=False)  # Название товара на 1688
    ozon_url = Column(String, nullable=False)  # Ссылка на Ozon
    alibaba_url = Column(String, nullable=False)  # Ссылка на 1688
    
    # Финансовые показатели (в USD)
    selling_price = Column(Float, nullable=False)  # Цена продажи (Ozon)
    purchase_price = Column(Float, nullable=False)  # Цена покупки (1688)
    marketplace_commission = Column(Float, nullable=False)  # Комиссия маркетплейса (27%)
    taxes = Column(Float, nullable=False)  # Налоги (7%)
    delivery_cost = Column(Float, nullable=False)  # Доставка по России (1.7 * вес)
    packaging_cost = Column(Float, nullable=False)  # Расходные материалы (фиксированные $0.1)
    agent_commission = Column(Float, nullable=False)  # Комиссия агента (5% от цены покупки)
    
    # Итоговые показатели
    total_profit = Column(Float, nullable=False)  # Итоговая прибыль
    profitability_percent = Column(Float, nullable=False)  # Маржинальность в %
    
    # Дополнительная информация
    weight = Column(Float)  # Вес товара
    dimensions = Column(String)  # Габариты товара
    
    # Дата создания записи
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с таблицей соответствий
    matched_product = relationship("MatchedProduct")
    
    def __repr__(self):
        return f"<ProductProfitability(id={self.id}, profit=${self.total_profit:.2f}, margin={self.profitability_percent:.2f}%)>"

class Task(Base):
    """
    Модель для хранения задач на обработку
    
    Возможные статусы задачи:
    - pending: Задача ожидает обработки (начальный статус)
    - ozon_processed: Данные с Ozon получены, ожидается поиск на Alibaba
    - completed: Задача успешно выполнена, товар найден на Alibaba
    - not_found: Товар не найден на Alibaba после всех попыток поиска
    - error: Ошибка при обработке задачи (не критическая)
    - failed: Ошибка при обработке задачи (критическая)
    - fatal: Неустранимая ошибка, требуется вмешательство администратора
    """
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False)
    status = Column(String, nullable=False, default='pending')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь с продуктом
    product = relationship("OzonProduct", back_populates="task", uselist=False) 