#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import create_engine, and_, func
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.core.models import Base, MatchedProduct, Task, OzonProduct, AlibabaProduct, ProductProfitability, User
from src.utils.logger import logger
from datetime import datetime, timedelta
import re
import json
import os

from src.utils.utils import convert_price_to_usd

class Database:
    def __init__(self, db_path="Ozon1688.db"):
        """
        Инициализация базы данных
        
        :param db_path: Путь к файлу базы данных
        """
        try:
            self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
            self.session_factory = sessionmaker(bind=self.engine)
            self.Session = scoped_session(self.session_factory)
            Base.metadata.create_all(self.engine)
            logger.debug("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка при инициализации базы данных: {e}")
    
    def get_session(self):
        """
        Получение сессии базы данных
        
        :return: Сессия SQLAlchemy
        """
        return self.Session()
    
    def close_session(self):
        """Закрытие текущей сессии"""
        if self.Session:
            self.Session.remove()
    
    def add_task(self, url: str, user_id: int) -> bool:
        """
        Добавление новой задачи
        
        :param url: URL товара
        :param user_id: ID пользователя
        :return: True если добавление успешно, False если нет
        """
        session = self.get_session()
        try:
            task = Task(url=url, user_id=user_id)
            session.add(task)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при добавлении задачи: {e}")
            return False
        finally:
            session.close()
    
    def is_url_exists(self, url: str) -> bool:
        """
        Проверка существования URL в базе
        
        :param url: URL для проверки
        :return: True если URL существует, False если нет
        """
        session = self.get_session()
        try:
            exists = session.query(Task).filter(Task.url == url).first() is not None
            return exists
        finally:
            session.close()
    
    def get_task_id_by_url(self, url: str) -> int:
        """
        Получение ID задачи по URL
        
        :param url: URL товара
        :return: ID задачи
        """
        session = self.get_session()
        try:
            task = session.query(Task).filter(Task.url == url).first()
            return task.id if task else None
        finally:
            session.close()
    
    def get_task_url(self, task_id: int) -> str:
        """
        Получение URL по ID задачи
        
        :param task_id: ID задачи
        :return: URL товара
        """
        session = self.get_session()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            return task.url if task else None
        finally:
            session.close()
    
    def get_task(self, task_id: int):
        """
        Получение задачи по ID
        
        :param task_id: ID задачи
        :return: Объект задачи или None
        """
        session = self.get_session()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            return task
        except Exception as e:
            logger.error(f"Ошибка при получении задачи: {e}")
            return None
        finally:
            session.close()
    
    def get_task_analogs(self, task_id: int):
        """
        Получение аналогов товара по ID задачи
        
        :param task_id: ID задачи
        :return: Список аналогов или None
        """
        session = self.get_session()
        try:
            # Получаем товар Ozon для задачи
            ozon_product = session.query(OzonProduct).filter_by(task_id=task_id).first()
            if not ozon_product:
                return None
                
            # Получаем соответствия для этого товара
            matches = session.query(MatchedProduct).filter_by(ozon_product_id=ozon_product.id).all()
            if not matches:
                return None
                
            # Получаем аналоги из Alibaba
            analogs = []
            for match in matches:
                alibaba_product = session.query(AlibabaProduct).filter_by(id=match.alibaba_product_id).first()
                if alibaba_product:
                    # Получаем данные о прибыльности
                    profitability = session.query(ProductProfitability).filter_by(match_id=match.id).first()
                    
                    # Создаем объект аналога с нужными данными
                    analog = {
                        'title': alibaba_product.title,
                        'url': alibaba_product.url,
                        'price': alibaba_product.price_usd,
                        'profit': profitability.total_profit if profitability else 0,
                        'margin': profitability.profitability_percent if profitability else 0
                    }
                    analogs.append(analog)
            
            return analogs
            
        except Exception as e:
            logger.error(f"Ошибка при получении аналогов товара: {e}")
            return None
        finally:
            session.close()
    
    def save_product(self, product_data: dict, task_id: int) -> bool:
        """
        Сохранение данных о товаре в базу данных
        
        :param product_data: Словарь с данными о товаре
        :param task_id: ID задачи
        :return: True если сохранение успешно, False если нет
        """
        session = self.get_session()
        try:
            # Проверяем, существует ли уже такой товар
            existing_product = session.query(OzonProduct).filter_by(
                product_id=product_data.get('product_id')
            ).first()
            
            if existing_product:
                # Обновляем существующий товар
                existing_product.url = product_data.get('url')
                existing_product.product_name = product_data.get('product_name')
                existing_product.price_current = product_data.get('price_current')
                existing_product.price_original = product_data.get('price_original')
                existing_product.images = product_data.get('images', [])
                existing_product.characteristics = product_data.get('characteristics', {})
                existing_product.weight = product_data.get('weight') if product_data.get('weight') is not None else existing_product.weight  # Обновляем вес
                existing_product.dimensions = product_data.get('dimensions')  # Обновляем размеры
                existing_product.updated_at = datetime.now()
                existing_product.task_id = task_id
                
                session.commit()
                logger.info(f"Обновлен существующий товар: {product_data.get('product_name')}")
                return True
            
            # Создаем новый товар
            product = OzonProduct(
                product_id=product_data.get('product_id'),
                url=product_data.get('url'),
                product_name=product_data.get('product_name'),
                price_current=product_data.get('price_current'),
                price_original=product_data.get('price_original'),
                images=product_data.get('images', []),
                characteristics=product_data.get('characteristics', {}),
                weight=product_data.get('weight'),  # Сохраняем вес
                dimensions=product_data.get('dimensions'),  # Сохраняем размеры
                task_id=task_id
            )
            
            session.add(product)
            session.commit()
            logger.info(f"Сохранен новый товар: {product_data.get('product_name')}")
            return True
            
        except IntegrityError as e:
            logger.error(f"Ошибка уникальности при сохранении товара: {e}")
            session.rollback()
            return False
        except Exception as e:
            logger.error(f"Ошибка при сохранении товара: {e}")
            session.rollback()
            return False
    
    def get_pending_tasks(self, limit=None) -> list:
        """
        Получение списка необработанных задач
        
        :param limit: Ограничение на количество возвращаемых задач (не более N)
        :return: Список задач
        """
        session = None
        tasks = []
        try:
            session = self.get_session()
            
            # Строим запрос к БД
            query = session.query(Task).filter(
                # Получаем только задачи в статусе 'pending' или 'ozon_processed'
                # и исключаем задачи с завершенными статусами
                Task.status.in_(['pending', 'ozon_processed']),
                ~Task.status.in_(['completed', 'error', 'fatal', 'not_found', 'failed'])
            ).order_by(
                # Сначала задачи с более высоким приоритетом (pending)
                # затем по времени создания (сначала старые)
                Task.status.desc(), Task.created_at.asc()
            )
            
            # Применяем ограничение, если оно указано
            if limit and isinstance(limit, int) and limit > 0:
                query = query.limit(limit)
            
            # Получаем задачи из результатов запроса
            tasks = query.all()
            
            # Логируем результаты поиска
            if tasks:
                task_ids = [task.id for task in tasks]
                task_count = len(tasks)
                
                # Получаем статистику по задачам
                pending_count = len([t for t in tasks if t.status == 'pending'])
                ozon_processed_count = len([t for t in tasks if t.status == 'ozon_processed'])
                
                logger.info(f"Найдена {task_count} необработанная задача (pending: {pending_count}, ozon_processed: {ozon_processed_count})")
                logger.debug(f"Идентификатор найденной задачи: {task_ids}")
                
                # Обновляем updated_at для задач, чтобы отметить, что они в обработке
                for task in tasks:
                    task.updated_at = datetime.now()
                session.commit()
            else:
                logger.debug("Нет необработанных задач")
            
            return tasks
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка задач: {e}")
            if session:
                try:
                    session.rollback()
                except:
                    pass
            return []
            
        finally:
            pass
    
    def save_alibaba_product(self, product_data: dict) -> int:
        """
        Сохранение данных о продукте с 1688.com в базу данных
        
        :param product_data: Словарь с данными о продукте
        :return: ID созданного продукта или None в случае ошибки
        """
        session = self.get_session()
        try:
            # Проверка на наличие данных
            if not product_data or not isinstance(product_data, dict):
                logger.error(f"Некорректные данные продукта: {product_data}")
                return None
                
            # Получаем цену напрямую
            price_str = product_data.get('price', '0')
            
            # Подробное логирование для отладки
            logger.debug(f"Исходная цена продукта: '{price_str}', тип: {type(price_str)}")
            
            try:
                # Проверяем, что цена не равна 0 или '0' - дополнительная проверка
                if price_str == '0' or price_str == 0:
                    # Попытка получить цену из логов, если в данных она нулевая
                    logger.warning("Получена нулевая цена, проверяем данные товара полностью")
                    logger.debug(f"Полные данные товара: {product_data}")
                    
                    # Если цена в данных равна нулю, но в логах видно другое значение
                    # Это может означать, что цена была найдена, но не сохранена правильно
                    original_price = product_data.get('original_price', price_str)
                    if original_price and original_price != '0' and original_price != 0:
                        logger.info(f"Найдена оригинальная цена: {original_price}, используем её вместо нулевой")
                        price_str = original_price
                
                # Предварительная обработка для случаев, когда могла сохраниться только числовая часть
                # Убираем все нечисловые символы, кроме точки
                price_clean = ''.join(c for c in str(price_str) if c.isdigit() or c == '.')
                if price_clean and price_clean != '0':
                    logger.info(f"Очищенная цена: {price_clean}")
                    price_str = price_clean
                
                # Проверяем, что строка цены содержит числовое значение
                if not any(c.isdigit() for c in str(price_str)):
                    logger.warning(f"Строка цены '{price_str}' не содержит цифр, устанавливаем значение по умолчанию")
                    price_str = '0'
                
                # Используем улучшенную функцию convert_price_to_usd с указанием валюты
                price_usd = convert_price_to_usd(price_str, 'CNY')
                logger.info(f"Цена '{price_str}' успешно конвертирована в {price_usd} USD")
            except Exception as e:
                logger.error(f"Ошибка при конвертации цены '{price_str}': {e}")
                price_usd = 0.0  # Устанавливаем цену по умолчанию в случае ошибки
            
            # Обработка поля repurchase_rate (извлечение числа из строки)
            repurchase_rate_str = product_data.get('repurchase_rate', '0')
            repurchase_rate = 0.0
            
            try:
                if repurchase_rate_str and repurchase_rate_str != "Нет данных":
                    # Извлекаем только числовую часть из строки (например, из "复购率10.29%")
                    numbers = re.findall(r'[\d.]+', repurchase_rate_str)
                    if numbers:
                        repurchase_rate = float(numbers[0])
                        logger.debug(f"Преобразование показателя повторных покупок: '{repurchase_rate_str}' -> {repurchase_rate}")
                    else:
                        logger.warning(f"Не удалось извлечь числовое значение из '{repurchase_rate_str}', устанавливаем 0.0")
            except Exception as e:
                logger.error(f"Ошибка при обработке показателя повторных покупок '{repurchase_rate_str}': {e}")
            
            # Обработка поля shop_years (извлечение числа из строки)
            shop_years_str = product_data.get('shop_years', '0')
            shop_years = 0
            
            try:
                if shop_years_str and shop_years_str != "Нет данных":
                    # Извлекаем только числовую часть из строки (например, из "7年" или "已经营7年")
                    numbers = re.findall(r'\d+', shop_years_str)
                    if numbers:
                        shop_years = int(numbers[0])
                        logger.debug(f"Преобразование лет магазина: '{shop_years_str}' -> {shop_years}")
                    else:
                        logger.warning(f"Не удалось извлечь числовое значение из '{shop_years_str}', устанавливаем 0")
            except Exception as e:
                logger.error(f"Ошибка при обработке лет магазина '{shop_years_str}': {e}")
            
            # Обработка поля sales (извлечение числа из строки продаж)
            sales_str = product_data.get('sales', '0')
            sales = 0
            
            try:
                if sales_str and sales_str != "Нет данных":
                    # Извлекаем только числовую часть из строки (например, из "已售1万+件" или "月销量 1500件")
                    # Проверяем наличие символа "万" (десять тысяч) для китайских чисел
                    if '万' in sales_str:
                        # Если есть "万", то умножаем на 10000
                        numbers = re.findall(r'[\d.]+', sales_str)
                        if numbers:
                            sales = int(float(numbers[0]) * 10000)
                            logger.debug(f"Преобразование продаж с '万': '{sales_str}' -> {sales}")
                    else:
                        # Обычное извлечение числа
                        numbers = re.findall(r'\d+', sales_str)
                        if numbers:
                            sales = int(numbers[0])
                            logger.debug(f"Преобразование продаж: '{sales_str}' -> {sales}")
                        else:
                            logger.warning(f"Не удалось извлечь числовое значение из '{sales_str}', устанавливаем 0")
            except Exception as e:
                logger.error(f"Ошибка при обработке продаж '{sales_str}': {e}")
            
            # Проверяем, существует ли уже такой продукт
            url = product_data.get('url')
            if not url:
                logger.warning("URL продукта отсутствует, не можем проверить на дубликаты")
            else:
                existing_product = session.query(AlibabaProduct).filter_by(url=url).first()
                
                if existing_product:
                    # Обновляем существующий продукт
                    existing_product.title = product_data.get('title')
                    existing_product.price_usd = price_usd
                    existing_product.company_name = product_data.get('company_name')
                    existing_product.image_url = product_data.get('image_url')
                    existing_product.sales = sales
                    existing_product.shop_years = shop_years
                    existing_product.repurchase_rate = repurchase_rate
                    
                    session.commit()
                    logger.info(f"Обновлен существующий продукт: {product_data.get('title')} (ID: {existing_product.id})")
                    return existing_product.id
            
            # Создаем новый продукт
            product = AlibabaProduct(
                title=product_data.get('title'),
                url=product_data.get('url'),
                price_usd=price_usd,
                company_name=product_data.get('company_name'),
                image_url=product_data.get('image_url'),
                sales=sales,
                shop_years=shop_years,
                repurchase_rate=repurchase_rate,
                created_at=datetime.now()
            )
            
            session.add(product)
            session.commit()
            logger.info(f"Сохранен новый продукт с 1688.com: {product_data.get('title')} с ID {product.id}")
            return product.id
            
        except IntegrityError as e:
            logger.error(f"Ошибка уникальности при сохранении продукта: {e}")
            session.rollback()
            return None
        except Exception as e:
            logger.error(f"Ошибка при сохранении продукта: {e}")
            session.rollback()
            return None
    
    def save_match(self, match_data: dict) -> int:
        """
        Сохранение соответствия между товарами Ozon и 1688
        
        :param match_data: Словарь с данными соответствия
        :return: ID созданной записи или 0 в случае ошибки
        """
        session = None
        try:
            session = self.get_session()
            
            # Создаем объект MatchedProduct
            match = MatchedProduct(
                ozon_product_id=match_data['ozon_product_id'],
                alibaba_product_id=match_data['alibaba_product_id'],
                relevance_score=match_data.get('relevance_score', 0.0),
                match_status=match_data.get('match_status', 'found'),
                match_explanation=match_data.get('match_explanation', ''),
                weight=match_data.get('weight'),
                dimensions=match_data.get('dimensions')
            )
            
            # Сохраняем в БД
            session.add(match)
            session.commit()
            
            # Получаем ID созданной записи
            match_id = match.id
            
            logger.info(f"Создано соответствие между товарами: Ozon {match_data['ozon_product_id']} - 1688 {match_data['alibaba_product_id']} (ID: {match_id})")
            
            return match_id
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении соответствия: {e}")
            if session:
                session.rollback()
            return 0
        finally:
            if session:
                session.close()
    
    def calculate_profitability(self, match_id: int) -> bool:
        """
        Рассчитывает маржинальность для найденного соответствия
        
        :param match_id: ID соответствия
        :return: True если расчет выполнен успешно, иначе False
        """
        session = None
        try:
            logger.info(f"Расчет маржинальности для соответствия {match_id}")
            
            # Получаем данные о соответствии
            session = self.get_session()
            match = session.query(MatchedProduct).filter_by(id=match_id).first()
            
            if not match:
                logger.error(f"Соответствие с ID {match_id} не найдено")
                return False
            
            # Получаем данные о товарах
            ozon_product = session.query(OzonProduct).filter_by(id=match.ozon_product_id).first()
            alibaba_product = session.query(AlibabaProduct).filter_by(id=match.alibaba_product_id).first()
            
            if not ozon_product or not alibaba_product:
                logger.error(f"Товары для соответствия {match_id} не найдены")
                return False
            
            # Получаем вес для расчета стоимости доставки
            # Вес хранится в граммах, переводим в килограммы для расчета
            weight_grams = match.weight if match.weight and match.weight > 0 else 0
            weight_kg = weight_grams / 1000  # Переводим в килограммы
            dimensions = match.dimensions if match.dimensions else ""
            
            logger.info(f"Данные для расчета: вес = {weight_grams} г ({weight_kg} кг), габариты = {dimensions}")
            
            # Конвертируем цену Ozon из рублей в доллары для сравнения
            selling_price_usd = convert_price_to_usd(ozon_product.price_current, 'RUB')
            
            # Цена покупки на 1688 (уже в долларах)
            purchase_price = alibaba_product.price_usd
            
            # Комиссия маркетплейса (27% от цены продажи)
            marketplace_commission = selling_price_usd * 0.27
            
            # Налоги (7% от цены продажи)
            taxes = selling_price_usd * 0.07
            
            # Расходы на доставку по России (зависит от веса в кг)
            delivery_cost = 1.7 * weight_kg if weight_kg > 0 else 0
            
            # Расходные материалы (фиксированные $0.1)
            packaging_cost = 0.1
            
            # Комиссия агента (5% от цены покупки)
            agent_commission = purchase_price * 0.05
            
            # Расчет итоговых показателей
            total_profit = selling_price_usd - purchase_price - marketplace_commission - taxes - delivery_cost - packaging_cost - agent_commission
            
            # Расчет маржинальности в процентах
            profitability_percent = (total_profit / selling_price_usd) * 100
            
            # Создаем запись о маржинальности
            profitability = ProductProfitability(
                match_id=match_id,
                ozon_name=ozon_product.product_name,
                alibaba_name=alibaba_product.title,
                ozon_url=ozon_product.url,
                alibaba_url=alibaba_product.url,
                selling_price=selling_price_usd,
                purchase_price=purchase_price,
                marketplace_commission=marketplace_commission,
                taxes=taxes,
                delivery_cost=delivery_cost,
                packaging_cost=packaging_cost,
                agent_commission=agent_commission,
                total_profit=total_profit,
                profitability_percent=profitability_percent,
                weight=weight_grams,  # Сохраняем вес в граммах
                dimensions=dimensions
            )
            
            # Сохраняем запись в базе данных
            session.add(profitability)
            session.commit()
            
            logger.info(f"Рассчитана маржинальность для товаров: {ozon_product.product_name} / {alibaba_product.title}")
            logger.info(f"Итоговая прибыль: ${total_profit:.2f}, маржинальность: {profitability_percent:.2f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при расчете маржинальности: {e}")
            if session:
                session.rollback()
            return False
        finally:
            if session:
                session.close()
    
    def get_all_profitability_records(self) -> list:
        """
        Получение всех записей о маржинальности товаров
        
        :return: Список записей о маржинальности
        """
        session = None
        try:
            session = self.get_session()
            records = session.query(ProductProfitability).all()
            
            # Преобразуем записи в словари для удобства использования
            result = []
            for record in records:
                result.append({
                    'id': record.id,
                    'match_id': record.match_id,
                    'ozon_name': record.ozon_name,
                    'alibaba_name': record.alibaba_name,
                    'ozon_url': record.ozon_url,
                    'alibaba_url': record.alibaba_url,
                    'selling_price': record.selling_price,
                    'purchase_price': record.purchase_price,
                    'marketplace_commission': record.marketplace_commission,
                    'taxes': record.taxes,
                    'delivery_cost': record.delivery_cost,
                    'packaging_cost': record.packaging_cost,
                    'agent_commission': record.agent_commission,
                    'total_profit': record.total_profit,
                    'profitability_percent': record.profitability_percent,
                    'weight': record.weight,
                    'dimensions': record.dimensions,
                    'created_at': record.created_at.isoformat() if record.created_at else None
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении записей о маржинальности: {e}")
            return []
        finally:
            if session:
                session.close()
                
    def get_profitability_by_match_id(self, match_id: int) -> dict:
        """
        Получение записи о маржинальности товара по ID сопоставления
        
        :param match_id: ID записи о сопоставлении товаров
        :return: Словарь с данными о маржинальности или None
        """
        session = None
        try:
            session = self.get_session()
            record = session.query(ProductProfitability).filter_by(match_id=match_id).first()
            
            if not record:
                return None
            
            # Преобразуем запись в словарь
            result = {
                'id': record.id,
                'match_id': record.match_id,
                'ozon_name': record.ozon_name,
                'alibaba_name': record.alibaba_name,
                'ozon_url': record.ozon_url,
                'alibaba_url': record.alibaba_url,
                'selling_price': record.selling_price,
                'purchase_price': record.purchase_price,
                'marketplace_commission': record.marketplace_commission,
                'taxes': record.taxes,
                'delivery_cost': record.delivery_cost,
                'packaging_cost': record.packaging_cost,
                'agent_commission': record.agent_commission,
                'total_profit': record.total_profit,
                'profitability_percent': record.profitability_percent,
                'weight': record.weight,
                'dimensions': record.dimensions,
                'created_at': record.created_at.isoformat() if record.created_at else None
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении записи о маржинальности: {e}")
            return None
        finally:
            if session:
                session.close()

    def get_tasks_statistics(self, user_id: int = None) -> dict:
        """
        Получение статистики по задачам
        
        :param user_id: ID пользователя (опционально)
        :return: Словарь со статистикой
        """
        session = self.get_session()
        try:
            query = session.query(Task)
            if user_id:
                query = query.filter(Task.user_id == user_id)
            
            total_tasks = query.count()
            completed_tasks = query.filter(Task.status == 'completed').count()
            not_found_tasks = query.filter(Task.status == 'not_found').count()
            error_tasks = query.filter(Task.status == 'error').count()
            failed_tasks = query.filter(Task.status == 'failed').count()
            fatal_tasks = query.filter(Task.status == 'fatal').count()
            pending_tasks = query.filter(Task.status == 'pending').count()
            ozon_processed_tasks = query.filter(Task.status == 'ozon_processed').count()
            
            return {
                'total': total_tasks,
                'completed': completed_tasks,
                'not_found': not_found_tasks,
                'error': error_tasks,
                'failed': failed_tasks,
                'fatal': fatal_tasks,
                'pending': pending_tasks,
                'ozon_processed': ozon_processed_tasks
            }
        except Exception as e:
            logger.error(f"Ошибка при получении статистики задач: {e}")
            return {}
        finally:
            session.close()

    def get_product_info_by_url(self, url: str) -> dict:
        """
        Получение информации о товаре по URL
        
        :param url: URL товара
        :return: Словарь с информацией о товаре или None
        """
        session = None
        try:
            session = self.get_session()
            
            # Получаем задачу по URL
            task = session.query(Task).filter_by(url=url).first()
            if not task:
                return None
            
            # Получаем товар Ozon
            ozon_product = session.query(OzonProduct).filter_by(task_id=task.id).first()
            if not ozon_product:
                return None
            
            # Получаем соответствие
            matched_product = session.query(MatchedProduct).filter_by(ozon_product_id=ozon_product.id).first()
            if not matched_product:
                return None
            
            # Получаем товар 1688
            alibaba_product = session.query(AlibabaProduct).filter_by(id=matched_product.alibaba_product_id).first()
            if not alibaba_product:
                return None
            
            # Получаем информацию о прибыльности
            profitability = session.query(ProductProfitability).filter_by(match_id=matched_product.id).first()
            if not profitability:
                return None
            
            # Конвертируем цену Ozon из рублей в доллары
            ozon_price_usd = convert_price_to_usd(ozon_product.price_current, 'RUB')
            
            return {
                'ozon_name': ozon_product.product_name,
                'ozon_url': ozon_product.url,
                'ozon_price': ozon_product.price_current,
                'ozon_price_usd': round(ozon_price_usd, 2),
                'alibaba_name': alibaba_product.title,
                'alibaba_url': alibaba_product.url,
                'alibaba_price': alibaba_product.price_usd,
                'profitability_percent': round(profitability.profitability_percent, 2),
                'total_profit': round(profitability.total_profit, 2),
                'weight': ozon_product.weight,
                'dimensions': ozon_product.dimensions,
                'created_at': profitability.created_at.strftime('%d.%m.%Y %H:%M'),
                'status': task.status
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении информации о товаре: {e}")
            return None
        finally:
            if session:
                session.close()

    def get_task_status_by_url(self, url: str) -> str:
        """
        Получение статуса задачи по URL
        
        :param url: URL товара
        :return: Статус задачи или None если задача не найдена
        """
        session = self.get_session()
        try:
            task = session.query(Task).filter(Task.url == url).first()
            return task.status if task else None
        finally:
            session.close()

    def get_active_tasks(self) -> list:
        """
        Получение списка активных задач (в обработке)
        
        :return: Список активных задач с информацией о товарах
        """
        session = None
        try:
            session = self.get_session()
            
            # Получаем задачи в статусах pending и ozon_processed
            active_tasks = session.query(
                Task.id,
                Task.url,
                Task.status,
                Task.created_at,
                OzonProduct.product_name.label('ozon_name'),
                OzonProduct.url.label('ozon_url'),
                AlibabaProduct.title.label('alibaba_name'),
                AlibabaProduct.url.label('alibaba_url')
            ).outerjoin(
                OzonProduct,
                OzonProduct.task_id == Task.id
            ).outerjoin(
                MatchedProduct,
                MatchedProduct.ozon_product_id == OzonProduct.id
            ).outerjoin(
                AlibabaProduct,
                AlibabaProduct.id == MatchedProduct.alibaba_product_id
            ).filter(
                Task.status.in_(['pending', 'ozon_processed'])
            ).order_by(
                Task.created_at.desc()
            ).all()
            
            return [
                {
                    'task_id': task.id,
                    'url': task.url,
                    'status': task.status,
                    'created_at': task.created_at.strftime('%d.%m.%Y %H:%M'),
                    'ozon_name': task.ozon_name,
                    'ozon_url': task.ozon_url,
                    'alibaba_name': task.alibaba_name,
                    'alibaba_url': task.alibaba_url
                }
                for task in active_tasks
            ]
            
        except Exception as e:
            logger.error(f"Ошибка при получении активных задач: {e}")
            return []
        finally:
            if session:
                session.close()

    def add_user(self, telegram_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
        """
        Добавление нового пользователя
        
        :param telegram_id: ID пользователя в Telegram
        :param username: Имя пользователя в Telegram
        :param first_name: Имя пользователя
        :param last_name: Фамилия пользователя
        :return: Объект пользователя
        """
        session = self.get_session()
        try:
            # Проверяем, существует ли пользователь
            existing_user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if existing_user:
                # Обновляем только базовую информацию
                existing_user.username = username
                existing_user.first_name = first_name
                existing_user.last_name = last_name
                session.commit()
                return existing_user
            
            # Проверяем, является ли пользователь админом
            is_admin = str(telegram_id) in os.getenv('ADMIN_IDS', '').split(',')
            
            # Создаем данные пользователя
            user_data = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'is_admin': is_admin,
                'subscription_type': 'free' if not is_admin else 'unlimited',
                'requests_limit': 3 if not is_admin else None,
                'requests_used': 0,
                'notifications_enabled': True
            }
            
            # Создаем нового пользователя
            user = User(**user_data)
            session.add(user)
            session.commit()
            
            return user
            
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при добавлении пользователя: {e}")
            return None
        finally:
            session.close()

    def get_user_by_telegram_id(self, telegram_id: int) -> User:
        """
        Получение пользователя по Telegram ID
        
        :param telegram_id: ID пользователя в Telegram
        :return: Объект пользователя
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.telegram_id == telegram_id).first()
            if user:
                # Создаем новый объект с данными из базы
                user_data = {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_admin': user.is_admin,
                    'subscription_type': user.subscription_type,
                    'requests_limit': user.requests_limit,
                    'requests_used': user.requests_used,
                    'subscription_end': user.subscription_end,
                    'notifications_enabled': user.notifications_enabled
                }
                return User(**user_data)
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя: {e}")
            return None
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> User:
        """
        Получение пользователя по ID
        
        :param user_id: ID пользователя
        :return: Объект пользователя
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                # Создаем новый объект с данными из базы
                user_data = {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_admin': user.is_admin,
                    'subscription_type': user.subscription_type,
                    'requests_limit': user.requests_limit,
                    'requests_used': user.requests_used,
                    'subscription_end': user.subscription_end,
                    'notifications_enabled': user.notifications_enabled
                }
                return User(**user_data)
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении пользователя по ID: {e}")
            return None
        finally:
            session.close()

    def get_all_users(self) -> list:
        """
        Получение списка всех пользователей
        
        :return: Список пользователей
        """
        session = self.get_session()
        try:
            users = session.query(User).all()
            result = []
            
            for user in users:
                user_data = {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_admin': user.is_admin,
                    'subscription_type': user.subscription_type,
                    'requests_limit': user.requests_limit,
                    'requests_used': user.requests_used,
                    'subscription_end': user.subscription_end,
                    'notifications_enabled': user.notifications_enabled
                }
                result.append(user_data)
                
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении списка пользователей: {e}")
            return []
        finally:
            session.close()

    def get_user_tasks(self, user_id: int, status: str = None) -> list:
        """
        Получение задач пользователя
        
        :param user_id: ID пользователя
        :param status: Статус задачи (опционально)
        :return: Список задач
        """
        session = self.get_session()
        try:
            logger.info(f"Получение задач для пользователя {user_id} со статусом {status}")
            
            query = session.query(Task).filter(Task.user_id == user_id)
            if status:
                if status == 'active':
                    # Для активных задач берем pending и ozon_processed
                    query = query.filter(Task.status.in_(['pending', 'ozon_processed']))
                else:
                    query = query.filter(Task.status == status)
            tasks = query.order_by(Task.created_at.desc()).all()
            
            logger.debug(f"Найдено {len(tasks)} задач")
            
            # Создаем список задач с необходимыми данными
            result = []
            for task in tasks:
                task_data = {
                    'id': task.id,
                    'url': task.url,
                    'status': task.status,
                    'created_at': task.created_at
                }
                result.append(task_data)
            
            logger.debug(f"Подготовлено {len(result)} задач для возврата")
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при получении задач пользователя: {e}")
            return []
        finally:
            session.close()

    def activate_subscription(self, user_id: int, subscription_type: str, days: int = 30, requests_limit: int = None, price: float = None) -> bool:
        """
        Активация подписки для пользователя
        
        :param user_id: ID пользователя
        :param subscription_type: Тип подписки ('limited' или 'unlimited')
        :param days: Количество дней подписки
        :param requests_limit: Лимит запросов для limited подписки
        :param price: Цена подписки
        :return: True если активация успешна, False если нет
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            # Устанавливаем дату окончания подписки
            user.subscription_end = datetime.now() + timedelta(days=days)
            user.subscription_type = subscription_type
            user.requests_limit = requests_limit
            user.requests_used = 0
            user.subscription_price = price
            
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при активации подписки: {e}")
            return False
        finally:
            session.close()

    def check_subscription(self, user_id: int) -> dict:
        """
        Проверяет статус подписки пользователя
        
        :param user_id: ID пользователя
        :return: Словарь с информацией о подписке
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return None
            
            # Если пользователь админ, у него всегда есть доступ
            if user.is_admin:
                return {
                    'is_active': True,
                    'type': 'admin',
                    'end_date': None,
                    'requests_left': None,
                    'requests_limit': None,
                    'requests_used': 0
                }
            
            # Проверяем срок действия подписки для платных подписок
            subscription_expired = False
            if user.subscription_type in ['limited', 'unlimited']:
                if user.subscription_end and user.subscription_end < datetime.now():
                    subscription_expired = True
            
            # Определяем количество оставшихся запросов
            requests_left = None
            if user.subscription_type in ['free', 'limited']:
                requests_left = max(0, user.requests_limit - user.requests_used)
            
            # Определяем активность подписки
            is_active = False
            
            # Для бесплатной подписки проверяем только количество запросов
            if user.subscription_type == 'free':
                is_active = user.requests_used < user.requests_limit
            
            # Для ограниченной подписки проверяем и срок, и количество запросов
            elif user.subscription_type == 'limited':
                is_active = not subscription_expired and user.requests_used < user.requests_limit
            
            # Для безлимитной подписки проверяем только срок
            elif user.subscription_type == 'unlimited':
                is_active = not subscription_expired
            
            return {
                'is_active': is_active,
                'type': user.subscription_type,
                'end_date': user.subscription_end,
                'requests_left': requests_left,
                'requests_limit': user.requests_limit,
                'requests_used': user.requests_used
            }
            
        except Exception as e:
            logger.error(f"Ошибка при проверке подписки: {e}")
            return None
        finally:
            session.close()

    def increment_requests_used(self, user_id: int) -> bool:
        """
        Увеличение счетчика использованных запросов
        
        :param user_id: ID пользователя
        :return: True если операция успешна, False если нет
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            # Если пользователь админ или у него unlimited подписка, не увеличиваем счетчик
            if user.is_admin or user.subscription_type == 'unlimited':
                return True
            
            # Проверяем, не превышен ли лимит
            if user.requests_limit is not None and user.requests_used >= user.requests_limit:
                logger.warning(f"Превышен лимит запросов для пользователя {user_id}: {user.requests_used}/{user.requests_limit}")
                return False
            
            # Увеличиваем счетчик использованных запросов
            user.requests_used += 1
            session.commit()
            logger.info(f"Увеличен счетчик запросов для пользователя {user_id}: {user.requests_used}/{user.requests_limit}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при увеличении счетчика запросов: {e}")
            return False
        finally:
            session.close()

    def decrement_requests_used(self, user_id: int) -> bool:
        """
        Уменьшение счетчика использованных запросов
        
        :param user_id: ID пользователя
        :return: True если операция успешна, False если нет
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            # Уменьшаем счетчик использованных запросов, но не меньше 0
            user.requests_used = max(0, user.requests_used - 1)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при уменьшении счетчика запросов: {e}")
            return False
        finally:
            session.close()

    def get_subscription_info(self) -> dict:
        """
        Получение информации о подписках
        
        :return: Словарь с информацией о подписках
        """
        return {
            'free': {
                'name': '🆓 Бесплатная',
                'price': 0,
                'requests': 3,
                'features': [
                    '3️⃣ бесплатных запроса',
                    '📊 Базовый анализ товаров',
                    '💰 Расчет маржинальности'
                ]
            },
            'limited': {
                'name': '💎 Расширенная',
                'price': 1000,  # Цена в рублях
                'requests': 100,  # Количество запросов
                'features': [
                    '💯 100 запросов в месяц',
                    '📈 Расширенный анализ товаров',
                    '⚡ Приоритетная обработка',
                    '🔔 Поддержка 24/7'
                ]
            },
            'unlimited': {
                'name': '👑 Безлимитная',
                'price': 3000,  # Цена в рублях
                'requests': '∞',
                'features': [
                    '♾️ Безлимитное количество запросов',
                    '🔍 Полный анализ товаров',
                    '🚀 Максимальный приоритет',
                    '👨‍💼 VIP поддержка 24/7',
                    '🔮 Доступ к новым функциям'
                ]
            }
        }

    def update_notifications_settings(self, user_id: int, enabled: bool) -> bool:
        """
        Обновляет настройки уведомлений пользователя
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.notifications_enabled = enabled
                session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при обновлении настроек уведомлений: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def get_notifications_settings(self, user_id: int) -> bool:
        """
        Получает настройки уведомлений пользователя
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user.notifications_enabled if user else True  # По умолчанию включено
        except Exception as e:
            logger.error(f"Ошибка при получении настроек уведомлений: {e}")
            return True  # По умолчанию включено
        finally:
            session.close()

    def reset_requests_used(self, user_id: int) -> bool:
        """
        Сброс счетчика использованных запросов
        
        :param user_id: ID пользователя
        :return: True если операция успешна, False если нет
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            
            user.requests_used = 0
            session.commit()
            logger.info(f"Сброшен счетчик запросов для пользователя {user_id}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при сбросе счетчика запросов: {e}")
            return False
        finally:
            session.close()

    def update_task_status(self, task_id: int, status: str) -> bool:
        """
        Обновление статуса задачи
        
        :param task_id: ID задачи
        :param status: Новый статус задачи
        :return: True если обновление успешно, False если нет
        """
        session = self.get_session()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
            
            task.status = status
            task.updated_at = datetime.now()
            session.commit()
            logger.info(f"Обновлен статус задачи {task_id} на {status}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Ошибка при обновлении статуса задачи: {e}")
            return False
        finally:
            session.close()