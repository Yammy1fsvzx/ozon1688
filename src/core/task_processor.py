#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import time
from src.core.database import Database
from src.core.browser_manager import BrowserManager
from src.core.models import OzonProduct, Task, MatchedProduct, ProductProfitability
from src.core.ozon_process import OzonProcessor
from src.core.alibaba_process import AlibabaProcessor
from src.utils.logger import logger
from datetime import datetime
from src.core.ai_analyzer import AIAnalyzer
from src.utils.utils import convert_price_to_usd

class TaskProcessor:
    def __init__(self, db, browser_manager=None):
        """
        Инициализация процессора задач
        
        :param db: Экземпляр базы данных
        :param browser_manager: Менеджер браузера
        """
        self.db = db
        self.processing = False
        self.found_product = None  # Сохраняем найденный товар для последующего использования
        
        # Если браузер-менеджер не передан, создаем его
        if browser_manager is None:
            from src.core.browser_manager import BrowserManager
            self.browser_manager = BrowserManager()
        else:
            self.browser_manager = browser_manager
            
        logger.info("TaskProcessor инициализирован")
    
    async def process_task(self, task: Task) -> bool:
        """
        Обработка одной задачи, с учетом её текущего статуса:
        
        - Для задач в статусе 'pending': выполняется обработка страницы Ozon и сохранение данных.
          После успешной обработки статус меняется на 'ozon_processed'.
        
        - Для задач в статусе 'ozon_processed': выполняется поиск товара на 1688.com.
          При успешном поиске статус меняется на 'completed', иначе на 'not_found'.
        
        - Задачи в других статусах ('completed', 'error', 'fatal', 'not_found', 'failed') не обрабатываются.
        
        :param task: Объект задачи
        :return: True если задача успешно обработана, False если нет
        """
        driver = None
        session = None
        
        try:
            # Получаем свежую сессию для работы с БД
            session = self.db.get_session()
            
            # Получаем актуальный статус задачи
            current_status = task.status
            
            if current_status not in ['pending', 'ozon_processed']:
                logger.warning(f"Задача {task.id} находится в статусе '{current_status}', пропускаем обработку")
                return False
            
            # Проверяем, есть ли уже профит для этой задачи
            ozon_product = session.query(OzonProduct).filter_by(task_id=task.id).first()
            if ozon_product:
                # Проверяем наличие записи в ProductProfitability через MatchedProduct
                matched_product = session.query(MatchedProduct).filter_by(ozon_product_id=ozon_product.id).first()
                if matched_product:
                    profit_exists = session.query(ProductProfitability).filter_by(match_id=matched_product.id).first()
                    if profit_exists:
                        logger.info(f"Для задачи {task.id} уже существует расчет прибыльности, обновляем статус на completed")
                        task.status = 'completed'
                        session.commit()
                        return True
            
            logger.info(f"Начало обработки задачи {task.id} для URL: {task.url}")
            
            # Проверка валидности URL
            if not task.url or not task.url.startswith(('http://', 'https://')):
                logger.error(f"Некорректный URL задачи: {task.url}")
                task.status = 'failed'
                session.commit()
                return False
            
            # Шаг 1: Обработка Ozon (если задача еще не обработана)
            if current_status == 'pending':
                # Открываем браузер с повторными попытками
                max_attempts = 3
                browser_opened = False
                
                for attempt in range(1, max_attempts + 1):
                    try:
                        logger.info(f"Попытка {attempt}/{max_attempts} открыть браузер")
                        driver = self.browser_manager.open_browser()
                        browser_opened = True
                        break
                    except Exception as e:
                        logger.error(f"Ошибка при открытии браузера (попытка {attempt}/{max_attempts}): {e}")
                        if attempt < max_attempts:
                            await asyncio.sleep(5)  # Пауза перед следующей попыткой
                        else:
                            logger.error("Не удалось открыть браузер после всех попыток")
                            task.status = 'failed'
                            session.commit()
                            return False
                
                try:
                    # Переходим по URL с обработкой таймаута
                    try:
                        self.browser_manager.navigate_to_url(task.url)
                    except Exception as e:
                        logger.error(f"Ошибка при переходе по URL {task.url}: {e}")
                        task.status = 'failed'
                        session.commit()
                        return False
                    
                    # Создаем процессор Ozon и обрабатываем страницу
                    ozon_processor = OzonProcessor(driver)
                    
                    # Обрабатываем страницу с повторными попытками
                    ozon_data = None
                    for attempt in range(1, max_attempts + 1):
                        try:
                            logger.info(f"Попытка {attempt}/{max_attempts} обработать страницу Ozon")
                            ozon_data = ozon_processor.process_product_page()
                            if ozon_data:
                                break
                        except Exception as e:
                            logger.error(f"Ошибка при обработке страницы Ozon (попытка {attempt}/{max_attempts}): {e}")
                            if attempt < max_attempts:
                                await asyncio.sleep(3)  # Пауза перед следующей попыткой
                                # Обновляем страницу перед повторной попыткой
                                try:
                                    driver.refresh()
                                    await asyncio.sleep(2)
                                except:
                                    pass
                    
                    if not ozon_data:
                        logger.error(f"Не удалось получить данные о товаре для задачи {task.id}")
                        task.status = 'failed'
                        session.commit()
                        return False
                    
                    # Проверяем наличие обязательных полей в данных
                    required_fields = ['product_id', 'product_name', 'price_current', 'images']
                    missing_fields = [field for field in required_fields if not ozon_data.get(field)]
                    
                    if missing_fields:
                        logger.error(f"В данных Ozon отсутствуют обязательные поля: {', '.join(missing_fields)}")
                        task.status = 'failed'
                        session.commit()
                        return False
                    
                    # Сохраняем данные в базу с повторными попытками
                    save_success = False
                    for attempt in range(1, max_attempts + 1):
                        try:
                            logger.info(f"Попытка {attempt}/{max_attempts} сохранить данные Ozon в БД")
                            save_success = self.db.save_product(ozon_data, task.id)
                            if save_success:
                                break
                        except Exception as e:
                            logger.error(f"Ошибка при сохранении данных Ozon (попытка {attempt}/{max_attempts}): {e}")
                            if attempt < max_attempts:
                                await asyncio.sleep(2)  # Пауза перед следующей попыткой
                    
                    if not save_success:
                        logger.error(f"Не удалось сохранить данные Ozon в БД для задачи {task.id}")
                        task.status = 'failed'
                        session.commit()
                        return False
                    
                    # Обновляем статус задачи
                    task.status = 'ozon_processed'
                    session.commit()
                    logger.info(f"Задача {task.id} успешно обработана на Ozon")
                    
                    # Освобождаем ресурсы перед следующим этапом
                    self.browser_manager.close_browser()
                    driver = None
                    await asyncio.sleep(1)  # Небольшая пауза перед следующим этапом
                
                except Exception as e:
                    logger.error(f"Непредвиденная ошибка при обработке данных Ozon: {e}")
                    task.status = 'failed'
                    session.commit()
                    if driver:
                        self.browser_manager.close_browser()
                        driver = None
                    return False
            
            # Шаг 2: Поиск на Alibaba (для задач в статусе ozon_processed)
            if task.status == 'ozon_processed':
                # Получаем данные о товаре Ozon из базы
                ozon_product = session.query(OzonProduct).filter_by(task_id=task.id).first()
                
                if not ozon_product:
                    logger.error(f"Не найден товар Ozon для задачи {task.id}")
                    task.status = 'error'
                    session.commit()
                    return False
                
                # Проверяем наличие изображений
                if not ozon_product.images or len(ozon_product.images) == 0:
                    logger.warning(f"Нет изображений товара для поиска на 1688.com для задачи {task.id}")
                    task.status = 'error'
                    session.commit()
                    return False
                
                # Получаем ID продукта OZON для создания соответствия
                ozon_product_id = ozon_product.id
                logger.info(f"Найден OZON продукт с ID {ozon_product_id}")
                
                # Формируем данные для поиска
                search_data = {
                    'title': ozon_product.product_name,
                    'characteristics': ozon_product.characteristics,
                    'images': ozon_product.images
                }
                
                # Проверяем наличие первого изображения
                if not search_data['images'] or len(search_data['images']) == 0:
                    logger.error(f"Список изображений пуст для задачи {task.id}")
                    task.status = 'error'
                    session.commit()
                    return False
                
                search_data['image_url'] = search_data['images'][0]
                
                # Трехэтапный поиск на Alibaba
                relevant_product = None
                
                # Первая попытка: стандартный поиск по изображению
                try:
                    logger.info("Попытка 1: Базовый поиск по изображению...")
                    
                    # Открываем браузер для первой попытки
                    driver = self.browser_manager.open_browser()
                    alibaba_processor = AlibabaProcessor(driver, self.browser_manager)
                    
                    # Выполняем поиск
                    relevant_product = alibaba_processor.process_product(search_data)
                    
                    if relevant_product and isinstance(relevant_product, dict):
                        # Сохраняем результаты и закрываем ресурсы
                        logger.info(f"Найден релевантный товар при первой попытке поиска")
                        
                        # Запоминаем нужные значения
                        task_id = task.id
                        ozon_product_id_copy = ozon_product_id
                        
                        # Закрываем сессию и браузер
                        if session:
                            session.close()
                            session = None
                        
                        self.browser_manager.close_browser()
                        driver = None
                        
                        # Сохраняем результат в новой сессии
                        self.found_product = relevant_product
                        return self._save_alibaba_product(task_id)
                    
                except Exception as e:
                    logger.error(f"Ошибка при первой попытке поиска: {e}")
                    if driver:
                        self.browser_manager.close_browser()
                        driver = None
                    await asyncio.sleep(2)
                
                # Получаем свежий объект задачи перед следующей попыткой
                task_id = task.id
                task = session.query(Task).filter_by(id=task_id).first()
                if not task:
                    logger.error(f"Не удалось найти задачу с ID {task_id}")
                    return False
                
                # Вторая попытка: перезапускаем браузер и повторяем поиск по изображению
                try:
                    logger.info("Попытка 2: Повторный поиск по изображению после перезапуска браузера...")
                    
                    # Открываем браузер для второй попытки и сразу переходим на 1688.com
                    driver = self.browser_manager.open_browser()
                    self.browser_manager.navigate_to_url("https://www.1688.com/")
                    await asyncio.sleep(3)  # Даем время на загрузку страницы
                    
                    # Обработка возможных всплывающих окон и капчи перед поиском
                    alibaba_processor = AlibabaProcessor(driver, self.browser_manager)
                    
                    # Проверка и обработка капчи, если она появится
                    try:
                        logger.info("Проверка наличия окна капчи перед поиском")
                        alibaba_processor._close_popup_windows()
                        await asyncio.sleep(1)  # Короткая пауза после проверки
                    except Exception as captcha_error:
                        logger.warning(f"Ошибка при обработке капчи: {captcha_error}")
                    
                    # Повторяем поиск
                    relevant_product = alibaba_processor.process_product(search_data)
                    
                    if relevant_product and isinstance(relevant_product, dict):
                        # Сохраняем результаты и закрываем ресурсы
                        logger.info(f"Найден релевантный товар при второй попытке поиска")
                        
                        # Запоминаем нужные значения
                        task_id = task.id
                        
                        # Закрываем сессию и браузер
                        if session:
                            session.close()
                            session = None
                        
                        self.browser_manager.close_browser()
                        driver = None
                        
                        # Сохраняем результат в новой сессии
                        self.found_product = relevant_product
                        return self._save_alibaba_product(task_id)
                    
                except Exception as e:
                    logger.error(f"Ошибка при второй попытке поиска: {e}")
                    if driver:
                        self.browser_manager.close_browser()
                        driver = None
                    await asyncio.sleep(2)
                
                # Получаем свежий объект задачи перед следующей попыткой
                task_id = task.id
                task = session.query(Task).filter_by(id=task_id).first()
                if not task:
                    logger.error(f"Не удалось найти задачу с ID {task_id}")
                    return False
                
                # Третья попытка: поиск с использованием бренда
                try:
                    logger.info("Попытка 3: Поиск с использованием бренда...")
                    
                    # Извлекаем бренд из названия товара
                    ai_analyzer = AIAnalyzer()
                    
                    # Получаем свежий объект OzonProduct из сессии
                    ozon_product = session.query(OzonProduct).filter_by(id=ozon_product_id).first()
                    if not ozon_product:
                        logger.error(f"Не удалось найти продукт Ozon с ID {ozon_product_id}")
                        return False
                        
                    brand = ai_analyzer.extract_brand(ozon_product.product_name)
                    
                    if brand:
                        logger.info(f"Извлечен бренд для поиска: {brand}")
                        
                        # Открываем браузер для третьей попытки
                        driver = self.browser_manager.open_browser()
                        self.browser_manager.navigate_to_url("https://www.1688.com/")
                        await asyncio.sleep(3)
                        
                        # Проверяем капчу после загрузки страницы 1688.com
                        try:
                            logger.info("Проверка наличия капчи после загрузки 1688.com")
                            self.browser_manager.check_and_handle_captcha()
                        except Exception as captcha_error:
                            logger.warning(f"Ошибка при обработке капчи: {captcha_error}")
                        
                        alibaba_processor = AlibabaProcessor(driver, self.browser_manager)
                        
                        # Дополнительная проверка на капчу и всплывающие окна
                        try:
                            alibaba_processor._close_popup_windows()
                            await asyncio.sleep(1)
                        except Exception as popup_error:
                            logger.warning(f"Ошибка при обработке всплывающих окон: {popup_error}")
                        
                        # Добавляем бренд в данные для поиска
                        search_data['brand'] = brand
                        
                        # Выполняем поиск с брендом
                        relevant_product = alibaba_processor.process_product(search_data)
                        
                        if relevant_product and isinstance(relevant_product, dict):
                            self.browser_manager.close_browser()
                            driver = None
                            
                            # Получаем свежий объект задачи перед сохранением результатов
                            task_id = task.id
                            task = session.query(Task).filter_by(id=task_id).first()
                            if not task:
                                logger.error(f"Не удалось найти задачу с ID {task_id}")
                                return False
                                
                            # Успешно нашли товар на Alibaba
                            logger.info(f"Найден релевантный товар на 1688.com")
                            
                            # Сохраняем результаты в БД и закрываем сессию перед этим
                            task_id = task.id
                            ozon_product_id_copy = ozon_product_id
                            
                            # Закрываем сессию, чтобы избежать конфликтов
                            if session:
                                session.close()
                                session = None
                            
                            # Закрываем браузер
                            if driver:
                                self.browser_manager.close_browser()
                                driver = None
                            
                            # Сохраняем результат в новой сессии
                            self.found_product = relevant_product
                            return self._save_alibaba_product(task_id)
                    else:
                        logger.warning("Не удалось извлечь бренд из названия товара")
                    
                    # Закрываем браузер после последней попытки
                    if driver:
                        self.browser_manager.close_browser()
                        driver = None
                    
                except Exception as e:
                    logger.error(f"Ошибка при третьей попытке поиска: {e}")
                    if driver:
                        self.browser_manager.close_browser()
                        driver = None
                
                # Если все попытки не дали результата
                logger.error("Все попытки поиска не дали результата")
                task.status = 'not_found'
                session.commit()
                
                return True
            
            # Перед выходом из функции нужно закрыть сессию 
            # если дошли до сохранения результатов
            if session:
                session.close()
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при обработке задачи: {e}")
            if session:
                try:
                    task.status = 'error'
                    session.commit()
                except:
                    pass
                finally:
                    session.close()
            
            # Закрываем браузер если он был открыт
            if driver:
                try:
                    self.browser_manager.close_browser()
                except Exception as close_error:
                    logger.error(f"Ошибка при закрытии браузера: {close_error}")
            
            return False
        finally:
            # Гарантированное закрытие браузера в любом случае
            if driver or self.browser_manager.driver:
                try:
                    self.browser_manager.close_browser()
                except Exception as close_error:
                    logger.error(f"Ошибка при гарантированном закрытии браузера: {close_error}")
    
    def _save_alibaba_product(self, task_id):
        """
        Сохранение найденного товара с Alibaba и создание соответствия
        
        :param task_id: ID задачи
        :return: ID созданного соответствия или 0 в случае ошибки
        """
        try:
            logger.info(f"Сохранение релевантного товара для задачи {task_id}")
            
            # Создаем новую сессию для работы с базой данных
            session = self.db.get_session()
            
            # Проверяем, существует ли задача с указанным ID
            task = session.query(Task).filter_by(id=task_id).first()
            if not task:
                logger.error(f"Задача с ID {task_id} не найдена")
                session.close()
                return 0
            
            # Проверяем, найден ли товар
            if not self.found_product:
                logger.warning(f"Товар не найден для задачи {task_id}")
                task.status = "not_found"
                task.updated_at = datetime.now()
                session.commit()
                session.close()
                return 0
            
            # Сохраняем ссылку на "сырые данные" товара для отладки
            try:
                found_price = self.found_product.get('price', '0')
                if found_price != '0' and found_price != 0:
                    # Сохраняем цену, которая была найдена в оригинальных данных
                    logger.info(f"Добавляем оригинальную цену из найденного товара: {found_price}")
                    self.found_product['original_price'] = found_price
            except Exception as e:
                logger.error(f"Ошибка при сохранении оригинальной цены: {e}")
            
            # Проверяем обязательные поля товара
            for field in ['url', 'title']:
                if not self.found_product.get(field):
                    logger.error(f"Отсутствует обязательное поле '{field}' для товара")
                    task.status = "error"
                    task.error_message = f"Отсутствует обязательное поле '{field}' для товара"
                    task.updated_at = datetime.now()
                    session.commit()
                    session.close()
                    return 0
            
            # Сохраняем товар с Alibaba
            alibaba_product_id = self.db.save_alibaba_product(self.found_product)
            
            if not alibaba_product_id:
                logger.error("Ошибка при сохранении товара с Alibaba")
                task.status = "error"
                task.error_message = "Ошибка при сохранении товара с Alibaba"
                task.updated_at = datetime.now()
                session.commit()
                session.close()
                return 0
            
            # Получаем вес и размеры из данных о товаре Ozon
            weight = None
            dimensions = None
            ozon_product = None
            
            try:
                # Получаем данные о товаре Ozon
                ozon_product = session.query(OzonProduct).filter_by(task_id=task_id).first()
                if ozon_product:
                    weight = ozon_product.weight
                    dimensions = ozon_product.dimensions
                    ozon_product_id = ozon_product.id
                    logger.debug(f"Получены вес ({weight}) и размеры ({dimensions}) для товара Ozon ({ozon_product.id})")
                else:
                    logger.warning(f"Товар Ozon для задачи {task_id} не найден")
                    ozon_product_id = None
            except Exception as e:
                logger.error(f"Ошибка при получении веса и размеров: {e}")
                ozon_product_id = None
            
            # Если не удалось получить ID товара Ozon, задача завершается с ошибкой
            if not ozon_product_id:
                logger.error(f"Не удалось получить ID товара Ozon для задачи {task_id}")
                task.status = "error"
                task.error_message = "Не удалось получить ID товара Ozon"
                task.updated_at = datetime.now()
                session.commit()
                session.close()
                return 0
            
            # Создаем соответствие
            match_data = {
                'ozon_product_id': ozon_product_id,
                'alibaba_product_id': alibaba_product_id,
                'relevance_score': self.found_product.get('relevance_score', 0.0),
                'match_status': 'found',
                'match_explanation': self.found_product.get('explanation', ''),
                'weight': weight if weight is not None else 0.0,
                'dimensions': dimensions if dimensions else ""
            }
            
            # Сохраняем соответствие
            match_id = self.db.save_match(match_data)
            
            if not match_id:
                logger.error("Ошибка при сохранении соответствия")
                task.status = "error"
                task.error_message = "Ошибка при сохранении соответствия"
                task.updated_at = datetime.now()
                session.commit()
                session.close()
                return 0
            
            # Рассчитываем маржинальность
            self.db.calculate_profitability(match_id)
            
            # Обновляем статус задачи
            task.status = "completed"
            task.updated_at = datetime.now()
            session.commit()
            
            session.close()
            return match_id
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении товара и создании соответствия: {e}")
            try:
                # Попытка обновить статус задачи в случае ошибки
                session = self.db.get_session()
                task = session.query(Task).filter_by(id=task_id).first()
                if task:
                    task.status = "error"
                    task.error_message = str(e)
                    task.updated_at = datetime.now()
                    session.commit()
                session.close()
            except:
                pass
            return 0
    
    async def start(self):
        """
        Запуск процессора задач: обрабатывает задачи по одной в правильном порядке
        """
        self.processing = True
        logger.info("Запуск процессора задач (режим последовательной обработки)")
        
        error_backoff_time = 5  # Начальное время ожидания при ошибке в секундах
        max_error_backoff_time = 60  # Максимальное время ожидания при ошибках
        current_backoff_time = error_backoff_time
        errors_count = 0
        
        while self.processing:
            try:
                # Получаем только одну необработанную задачу с наивысшим приоритетом
                tasks = self.db.get_pending_tasks(limit=1)
                
                if tasks and len(tasks) > 0:
                    # Сбрасываем счетчик ошибок при успешном получении задачи
                    errors_count = 0
                    current_backoff_time = error_backoff_time
                    
                    # Получаем единственную задачу из списка
                    task = tasks[0]
                    
                    # Логируем информацию о задаче
                    logger.info(f"Начинаем обработку задачи {task.id} в статусе '{task.status}'")
                    
                    # Обрабатываем задачу
                    task_result = await self.process_task(task)
                    
                    if task_result:
                        logger.info(f"Задача {task.id} успешно обработана")
                    else:
                        logger.warning(f"Задача {task.id} не обработана")
                    
                    # Пауза после обработки задачи
                    await asyncio.sleep(2)
                    
                else:
                    # Если задач нет, ждем
                    await asyncio.sleep(5)
                    logger.debug("Нет необработанных задач, ожидание 5 секунд...")
                
            except Exception as e:
                # Увеличиваем счетчик ошибок и время ожидания при повторяющихся ошибках
                errors_count += 1
                current_backoff_time = min(current_backoff_time * 1.5, max_error_backoff_time)
                
                logger.error(f"Ошибка в основном цикле процессора (#{errors_count}): {str(e)}")
                logger.info(f"Ожидание {current_backoff_time} секунд перед повторной попыткой...")
                
                await asyncio.sleep(current_backoff_time)
                
                # Проверяем состояние соединения с БД при большом количестве ошибок
                if errors_count > 5:
                    try:
                        logger.warning("Проверка соединения с базой данных после нескольких ошибок...")
                        # Пробуем получить список задач, чтобы проверить соединение
                        self.db.get_pending_tasks(limit=1)
                        logger.info("Соединение с базой данных восстановлено")
                    except Exception as db_error:
                        logger.critical(f"Проблема с соединением с базой данных: {db_error}")
                        # Добавим дополнительную паузу при проблемах с БД
                        await asyncio.sleep(10)
    
    async def stop(self):
        """
        Остановка процессора задач
        """
        self.processing = False
        logger.info("Остановка процессора задач") 