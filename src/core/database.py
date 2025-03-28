#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import create_engine, and_, func
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.core.models import Base, MatchedProduct, Task, OzonProduct, AlibabaProduct, ProductProfitability
from src.utils.logger import logger
from datetime import datetime
import re
import json

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
    
    def add_task(self, url: str) -> bool:
        """
        Добавление новой задачи
        
        :param url: URL товара
        :return: True если добавление успешно, False если нет
        """
        session = self.get_session()
        try:
            # Проверяем, существует ли уже такая задача
            existing_task = session.query(Task).filter_by(url=url).first()
            if existing_task:
                logger.info(f"Удаляем существующую задачу для URL {url}")
                # Удаляем связанные товары
                session.query(OzonProduct).filter_by(task_id=existing_task.id).delete()
                # Удаляем саму задачу
                session.delete(existing_task)
                session.commit()
            
            # Создаем новую задачу
            task = Task(url=url, status='pending')
            session.add(task)
            session.commit()
            logger.info(f"Добавлена новая задача для URL: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении задачи: {e}")
            session.rollback()
            return False
    
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

    def get_tasks_statistics(self) -> dict:
        """
        Получение статистики по задачам
        
        :return: Словарь со статистикой
        """
        session = None
        try:
            session = self.get_session()
            
            # Получаем общее количество задач
            total_tasks = session.query(Task).count()
            
            # Получаем количество задач по статусам
            status_counts = {}
            for status in ['pending', 'ozon_processed', 'completed', 'error', 'fatal', 'not_found', 'failed']:
                count = session.query(Task).filter_by(status=status).count()
                status_counts[status] = count
            
            # Получаем количество успешно обработанных товаров (с маржинальностью)
            completed_products = session.query(ProductProfitability).count()
            
            # Получаем среднюю маржинальность
            avg_profitability = session.query(func.avg(ProductProfitability.profitability_percent)).scalar()
            if avg_profitability:
                avg_profitability = round(avg_profitability, 2)
            
            # Получаем последние 5 обработанных товаров
            last_products = session.query(
                OzonProduct.product_name,
                OzonProduct.url.label('ozon_url'),
                AlibabaProduct.url.label('alibaba_url'),
                ProductProfitability.profitability_percent,
                ProductProfitability.created_at
            ).join(
                MatchedProduct,
                MatchedProduct.ozon_product_id == OzonProduct.id
            ).join(
                AlibabaProduct,
                AlibabaProduct.id == MatchedProduct.alibaba_product_id
            ).join(
                ProductProfitability,
                ProductProfitability.match_id == MatchedProduct.id
            ).order_by(
                ProductProfitability.created_at.desc()
            ).limit(5).all()
            
            return {
                'total_tasks': total_tasks,
                'status_counts': status_counts,
                'completed_products': completed_products,
                'avg_profitability': avg_profitability,
                'last_products': [
                    {
                        'name': p.product_name,
                        'ozon_url': p.ozon_url,
                        'alibaba_url': p.alibaba_url,
                        'profitability': round(p.profitability_percent, 2),
                        'created_at': p.created_at.strftime('%d.%m.%Y %H:%M')
                    }
                    for p in last_products
                ]
            }
            
        except Exception as e:
            logger.error(f"Ошибка при получении статистики: {e}")
            return None
        finally:
            if session:
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