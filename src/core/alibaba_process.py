#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import requests
import json
import random
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.action_chains import ActionChains
from src.utils.logger import logger
from src.core.ai_analyzer import AIAnalyzer
import asyncio
import re
import signal
import atexit

class AlibabaProcessor:
    """
    Класс для обработки поиска товаров на 1688.com
    """
    
    def __init__(self, driver, browser_manager, timeout=30):
        """
        Инициализация процессора
        
        :param driver: WebDriver
        :param browser_manager: Экземпляр BrowserManager
        :param timeout: Таймаут ожидания элементов
        """
        self.driver = driver
        self.browser_manager = browser_manager
        self.wait = WebDriverWait(driver, timeout)
        self.temp_folder = "temp"
        
        # Создаем временную директорию, если её нет
        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder)
        
        # Регистрируем обработчики для корректного закрытия браузера
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.debug(f"Инициализация AlibabaProcessor (timeout={timeout})")
    
    def _cleanup(self):
        """
        Метод для очистки ресурсов при завершении
        """
        try:
            # Закрываем браузер
            if self.browser_manager:
                logger.info("Закрываем браузер при завершении работы")
                self.browser_manager.close_browser()
            
            # Очищаем временную директорию
            self._clear_temp_folder()
        except Exception as e:
            logger.error(f"Ошибка при очистке ресурсов: {e}")
    
    def _clear_temp_folder(self):
        """
        Очистка временной директории от изображений
        """
        try:
            if os.path.exists(self.temp_folder):
                for file in os.listdir(self.temp_folder):
                    file_path = os.path.join(self.temp_folder, file)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                            logger.debug(f"Удален временный файл: {file_path}")
                    except Exception as e:
                        logger.error(f"Ошибка при удалении файла {file_path}: {e}")
                logger.info("Временная директория очищена")
        except Exception as e:
            logger.error(f"Ошибка при очистке временной директории: {e}")
    
    def _signal_handler(self, signum, frame):
        """
        Обработчик сигналов для корректного завершения
        """
        logger.info(f"Получен сигнал {signum}, закрываем браузер...")
        self._cleanup()
        # Пробрасываем сигнал дальше для завершения программы
        signal.default_int_handler(signum, frame)
    
    def close(self):
        """
        Явное закрытие браузера
        """
        self._cleanup()
    
    def download_image(self, image_url: str) -> str:
        """
        Скачивание изображения во временную директорию
        
        :param image_url: URL изображения
        :return: Путь к сохраненному файлу
        """
        try:
            # Создаем временную директорию, если её нет
            if not os.path.exists(self.temp_folder):
                os.makedirs(self.temp_folder)
            
            # Генерируем уникальное имя файла
            timestamp = int(time.time())
            file_extension = os.path.splitext(image_url)[1]
            if not file_extension:
                file_extension = '.jpg'
            temp_filename = f"temp_image_{timestamp}{file_extension}"
            temp_path = os.path.join(self.temp_folder, temp_filename)
            
            # Скачиваем изображение
            response = requests.get(image_url, stream=True)
            response.raise_for_status()
            
            # Сохраняем файл
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            # Возвращаем абсолютный путь к файлу
            return os.path.abspath(temp_path)
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании изображения: {e}")
            return None
    
    def _retry_with_popup_checks(self, action_function, max_attempts=3, wait_between=1):
        """
        Выполняет указанную функцию с повторными попытками
        и минимальными проверками на всплывающие окна
        
        :param action_function: Функция для выполнения
        :param max_attempts: Максимальное количество попыток
        :param wait_between: Время ожидания между попытками в секундах
        :return: Результат функции или None в случае ошибки
        """
        for attempt in range(1, max_attempts + 1):
            try:
                # Быстрая проверка всплывающих окон только перед первой попыткой
                if attempt == 1:
                    self._close_popup_windows()
                
                # Выполняем нужное действие
                result = action_function()
                
                # Если успешно - возвращаем результат
                return result
                
            except Exception as e:
                # Проверяем всплывающие окна только после неудачной попытки
                self._close_popup_windows()
                
                # Если это последняя попытка - выходим с ошибкой
                if attempt == max_attempts:
                    return None
                
                # Иначе ждем и пробуем снова
                time.sleep(wait_between)
        
        return None

    def _handle_browser_permissions(self):
        """
        Обрабатывает настройки разрешений браузера, включая разрешение всплывающих окон
        и доступ к загрузке изображений
        """
        try:
            # Проверяем наличие модального окна о блокировке
            blocked_popup_xpath = "//div[contains(text(), 'заблокированы') or contains(text(), 'blocked')]"
            
            # Проверяем с коротким таймаутом наличие окна
            try:
                popup_message = WebDriverWait(self.driver, 1).until(
                    EC.presence_of_element_located((By.XPATH, blocked_popup_xpath))
                )
                
                logger.info("Обнаружено окно о блокировке всплывающих окон")
                
                # Находим все кнопки в окне
                dialog_buttons = self.driver.find_elements(By.TAG_NAME, "button")
                
                # Сначала пробуем найти кнопку "Управление"
                manage_clicked = False
                for button in dialog_buttons:
                    if "правл" in button.text or "anage" in button.text or "настро" in button.text:
                        logger.info("Нажимаем кнопку 'Управление'")
                        try:
                            button.click()
                            manage_clicked = True
                            time.sleep(1)
                            break
                        except:
                            continue
                            
                # Затем пробуем найти кнопку "Готово" или любую другую для закрытия
                if manage_clicked:
                    # Получаем обновленный список кнопок после нажатия "Управление"
                    buttons_after = self.driver.find_elements(By.TAG_NAME, "button")
                    for button in buttons_after:
                        if "отово" in button.text or "Gotit" in button.text or "ontinue" in button.text or "азре" in button.text:
                            logger.info(f"Нажимаем на кнопку: {button.text}")
                            try:
                                button.click()
                                time.sleep(0.5)
                                break
                            except:
                                continue
                
                # Если не нашли кнопку управления, пробуем просто закрыть
                if not manage_clicked:
                    logger.info("Пробуем просто закрыть окно блокировки")
                    # Пробуем найти любую кнопку закрытия
                    for button in dialog_buttons:
                        try:
                            button.click()
                            time.sleep(0.5)
                            logger.info("Нажали кнопку в окне блокировки")
                            break
                        except:
                            continue
                
                # Проверяем, исчезло ли окно
                try:
                    WebDriverWait(self.driver, 1).until_not(
                        EC.presence_of_element_located((By.XPATH, blocked_popup_xpath))
                    )
                    logger.info("Окно блокировки закрыто успешно")
                except:
                    logger.warning("Окно блокировки может все еще присутствовать")
                
                # Попробуем нажать на элементы страницы или клавиши Escape для закрытия
                try:
                    ActionChains(self.driver).send_keys('\ue00c').perform()  # Escape
                    time.sleep(0.5)
                except:
                    pass
                
            except:
                # Окно блокировки не найдено
                pass
                
            # Проверяем наличие настроек сайта в браузере через JavaScript
            try:
                # Пытаемся программно разрешить всплывающие окна через JavaScript
                script = """
                try {
                    // Пытаемся разрешить всплывающие окна и уведомления
                    if (navigator.permissions) {
                        navigator.permissions.query({name: 'notifications'}).then(function(result) {
                            if (result.state === 'prompt' || result.state === 'denied') {
                                console.log('Attempting to allow notifications');
                            }
                        });
                    }
                    return true;
                } catch (e) {
                    console.error('Error:', e);
                    return false;
                }
                """
                self.driver.execute_script(script)
            except:
                pass
                
            return True
                
        except Exception as e:
            logger.warning(f"Ошибка при обработке настроек браузера: {e}")
            return False

    def search_by_image(self, image_path: str) -> bool:
        """
        Поиск товаров по изображению на 1688.com
        
        :param image_path: Путь к изображению
        :return: True если поиск успешно выполнен, False если нет
        """
        try:
            # Сохраняем исходные вкладки
            original_windows = self.driver.window_handles
            
            # Переходим на главную страницу 1688.com
            logger.info("Переход на 1688.com")
            self.driver.get("https://www.1688.com/")
            
            # Однократная проверка на всплывающие окна после загрузки страницы
            time.sleep(1)
            self._close_popup_windows()
            
            # Быстрая проверка на блокировку всплывающих окон
            self._handle_browser_permissions()
            
            # Находим кнопку поиска по изображению и выполняем загрузку
            try:
                upload_button = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "img-search-upload"))
                )
                upload_button.send_keys(image_path)
                logger.info("Изображение загружено для поиска")
            except Exception as e:
                # В случае ошибки - закрываем возможные окна и пробуем снова
                self._close_popup_windows()
                try:
                    upload_button = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "img-search-upload"))
                    )
                    upload_button.send_keys(image_path)
                    logger.info("Изображение загружено для поиска (2-я попытка)")
                except:
                    logger.error("Не удалось загрузить изображение после двух попыток")
                    return False
            
            # Запоминаем текущий URL
            current_url = self.driver.current_url
            
            # Ждем результаты поиска с минимальным количеством проверок окон
            wait_time = 0
            max_wait_time = 30
            
            while wait_time < max_wait_time:
                # Проверяем всплывающие окна только каждые 10 секунд
                if wait_time % 10 == 0:
                    self._close_popup_windows()
                
                # Проверяем наличие новой вкладки
                if len(self.driver.window_handles) > len(original_windows):
                    logger.info(f"Найдена новая вкладка после {wait_time} секунд ожидания")
                    # Определяем новую вкладку с результатами поиска
                    search_results_window = None
                    for window in self.driver.window_handles:
                        if window not in original_windows:
                            search_results_window = window
                            break
                        
                    if search_results_window:
                        # Переключаемся на вкладку с результатами
                        self.driver.switch_to.window(search_results_window)
                        break
                
                # Проверяем изменение URL в текущей вкладке
                try:
                    if self.driver.current_url != current_url and "1688.com" in self.driver.current_url:
                        logger.info(f"URL изменился в текущей вкладке после {wait_time} секунд ожидания")
                        break
                except:
                    pass
                
                # Проверяем наличие результатов поиска на странице
                try:
                    search_results = self.driver.find_elements(By.CSS_SELECTOR, ".space-offer-card-box, .space-offer-card, .sm-offer-item, .offer-item, .card-container")
                    if search_results and len(search_results) > 0:
                        logger.info(f"Обнаружены результаты поиска в текущей вкладке после {wait_time} секунд ожидания")
                        break
                except:
                    pass
                
                time.sleep(1)
                wait_time += 1
            
            # После нахождения результатов, ожидаем полную загрузку страницы и обрабатываем товары
            try:
                # Ждем полной загрузки страницы результатов
                WebDriverWait(self.driver, 10).until(
                    lambda driver: driver.execute_script("return document.readyState") == "complete"
                )
                
                # Проверяем наличие результатов поиска
                search_results = self.driver.find_elements(By.CSS_SELECTOR, ".space-offer-card-box, .space-offer-card, .sm-offer-item, .offer-item, .card-container, .normalcommon-offer-card")
                if search_results and len(search_results) > 0:
                    logger.info(f"Найдено {len(search_results)} результатов поиска")
                    
                    # Закрываем возможные окна перед обработкой результатов
                    self._close_popup_windows()
                    
                    return True
                else:
                    logger.warning("Не удалось найти результаты поиска")
                    return False
                
            except Exception as e:
                logger.error(f"Ошибка при ожидании загрузки страницы результатов: {e}")
                return False
            
        except Exception as e:
            logger.error(f"Ошибка при поиске по изображению: {str(e)}")
            return False
    
    def process_product(self, ozon_product: dict) -> dict:
        """
        Обработка товара: скачивание изображения, поиск на 1688.com и анализ релевантности
        
        :param ozon_product: Словарь с данными о товаре с Ozon
        :return: Словарь с результатами поиска и анализа или None
        """
        browser_closed = False
        image_path = None
        
        try:
            logger.info("Начинаем обработку товара...")
            
            # Получаем URL изображения из данных товара
            image_url = ozon_product.get('image_url')
            if not image_url and 'images' in ozon_product and ozon_product['images']:
                image_url = ozon_product['images'][0]
            
            if not image_url:
                logger.error("URL изображения не найден в данных товара")
                return None
            
            # Скачиваем изображение
            logger.info(f"Скачиваем изображение товара: {image_url}")
            image_path = self.download_image(image_url)
            if not image_path:
                logger.error("Не удалось скачать изображение")
                return None
            
            # Создаем анализатор
            ai_analyzer = AIAnalyzer()
            
            try:
                # Выполняем поиск на 1688.com
                if not self.search_by_image(image_path):
                    logger.error("Не удалось выполнить поиск по изображению")
                    self._cleanup()
                    browser_closed = True
                    return None
                
                # Получаем все найденные товары
                alibaba_products = self.process_product_cards()
                if not alibaba_products:
                    logger.warning("Товары не найдены на 1688.com")
                    self._cleanup()
                    browser_closed = True
                    return None
                
                logger.info(f"Найдено {len(alibaba_products)} товаров")
                
                # Анализируем релевантность ВСЕХ товаров за один раз
                analysis_result = ai_analyzer.analyze_relevance(
                    ozon_product=ozon_product,
                    alibaba_products=alibaba_products,
                    threshold=60
                )
                
                # После получения результатов анализа закрываем браузер
                self._cleanup()
                browser_closed = True
                
                if analysis_result:
                    # Получаем индекс лучшего товара из результата анализа
                    product_index = analysis_result.get('product_index', 0)
                    
                    # Получаем сам товар из списка
                    best_product = alibaba_products[product_index]
                    
                    # Добавляем информацию о релевантности из результата анализа
                    best_product['relevance_score'] = analysis_result.get('relevance_score', 0)
                    best_product['explanation'] = analysis_result.get('explanation', '')
                    
                    logger.info(f"Найден релевантный товар с оценкой {best_product['relevance_score']}")
                    return best_product
                
                logger.info("Релевантные товары не найдены")
                return None
                
            except Exception as browser_error:
                logger.error(f"Ошибка при работе с браузером: {browser_error}")
                if not browser_closed:
                    self._cleanup()
                raise
            
        except Exception as e:
            logger.error(f"Ошибка при обработке товара: {str(e)}")
            if not browser_closed:
                self._cleanup()
            return None
        
        finally:
            # Удаляем временное изображение
            if image_path and os.path.exists(image_path):
                try:
                    os.unlink(image_path)
                    logger.debug(f"Удалено временное изображение: {image_path}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении временного изображения {image_path}: {e}")
            
            # Гарантируем закрытие браузера в любом случае
            if not browser_closed:
                self._cleanup()
    
    def wait_for_page_to_load(self, timeout=30):
        """
        Ожидание полной загрузки страницы
        
        :param timeout: Максимальное время ожидания в секундах
        """
        try:
            # Ждем, пока страница полностью загрузится
            WebDriverWait(self.driver, timeout).until(
                lambda driver: driver.execute_script("return document.readyState") == "complete"
            )
            
            # Даем дополнительное время для загрузки динамического контента
            time.sleep(2)
            
            # Проверяем наличие результатов поиска
            try:
                search_results = self.driver.find_elements(By.CSS_SELECTOR, ".space-offer-card-box, .space-offer-card, .sm-offer-item, .offer-item, .card-container")
                if search_results:
                    logger.info(f"Найдено {len(search_results)} результатов поиска")
                    return True
            except:
                pass
            
            logger.warning("Не удалось найти результаты поиска на странице")
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при ожидании загрузки страницы: {e}")
            return False
    
    def process_product_cards(self) -> list:
        """
        Обработка карточек товаров на странице результатов
        
        :return: Список обработанных товаров
        """
        try:
            # Ждем появления карточек товаров
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "normalcommon-offer-card"))
            )
            
            # Получаем все карточки товаров
            product_cards = self.driver.find_elements(By.CLASS_NAME, "normalcommon-offer-card")
            
            # Ограничиваем количество карточек до 15
            product_cards = product_cards[:15]
            logger.info(f"Ограничиваем количество товаров до {len(product_cards)}")
            
            processed_products = []
            
            for card in product_cards:
                try:
                    # Базовые данные о товаре, которые мы всегда получаем
                    product_data = {
                        'title': self._get_text_or_default(card, ".mojar-element-title .title", "Без названия"),
                        'url': self._get_attribute_or_default(card, ".mojar-element-title a", "href", "#"),
                        'company_name': self._get_text_or_default(card, ".mojar-element-company .company-name", "Неизвестно"),
                        'sales': self._get_text_or_default(card, ".mojar-element-price .count", "Нет данных"),
                        'shop_years': self._get_text_or_default(card, ".credit-tag", "Нет данных"),
                        'repurchase_rate': self._get_text_or_default(card, ".shop-repurchase-rate", "Нет данных")
                    }
                    
                    # Обработка URL изображения
                    try:
                        img_style = card.find_element(By.CSS_SELECTOR, ".img").get_attribute('style')
                        if 'url(' in img_style:
                            img_url = img_style.split('url("')[1].split('")')[0]
                            product_data['image_url'] = img_url
                        else:
                            product_data['image_url'] = ""
                    except:
                        product_data['image_url'] = ""
                    
                    # Разные способы получения цены - поддержка разных версий разметки
                    price = "0"
                    price_found = False
                    
                    # Способ 1: Стандартный .mojar-element-price .price
                    try:
                        price_element = card.find_element(By.CSS_SELECTOR, ".mojar-element-price .price")
                        if price_element:
                            price = price_element.text.strip()
                            price_found = True
                            logger.debug(f"Нашли цену способом 1: {price}")
                    except:
                        pass
                    
                    # Способ 2: Через JavaScript (более надежный)
                    if not price_found:
                        try:
                            # Получить элемент через JS и извлечь текст
                            price = self.driver.execute_script("""
                                var card = arguments[0];
                                var priceDiv = card.querySelector('.mojar-element-price .price');
                                return priceDiv ? priceDiv.textContent.trim() : '0';
                            """, card)
                            
                            if price and price != '0':
                                price_found = True
                                logger.debug(f"Нашли цену способом 2: {price}")
                        except:
                            pass
                    
                    # Способ 3: Попытка найти в дочерних элементах
                    if not price_found:
                        try:
                            price_container = card.find_element(By.CSS_SELECTOR, ".mojar-element-price")
                            # Ищем все возможные элементы с числами
                            price_candidates = price_container.find_elements(By.XPATH, ".//*[contains(text(), '¥') or contains(@class, 'price')]")
                            
                            for candidate in price_candidates:
                                candidate_text = candidate.text.strip()
                                # Проверяем, содержит ли текст цифры
                                if any(c.isdigit() for c in candidate_text):
                                    # Извлекаем только цифры и точки
                                    price = ''.join(c for c in candidate_text if c.isdigit() or c == '.')
                                    price_found = True
                                    logger.debug(f"Нашли цену способом 3: {price} из {candidate_text}")
                                    break
                        except:
                            pass
                    
                    # Способ 3.5: Поиск по showPrice (часто встречается на 1688)
                    if not price_found:
                        try:
                            # Ищем элементы с классом showPrice
                            show_price_elements = card.find_elements(By.XPATH, ".//*[contains(@class, 'showPrice') or contains(@class, 'price-original') or contains(@class, 'price-discount') or contains(@class, 'price-current')]")
                            for show_price in show_price_elements:
                                price_text = show_price.text.strip()
                                if price_text and any(c.isdigit() for c in price_text):
                                    # Извлекаем только цифры и точки
                                    price_digits = ''.join(c for c in price_text if c.isdigit() or c == '.')
                                    if price_digits:
                                        price = price_digits
                                        price_found = True
                                        logger.debug(f"Нашли цену способом 3.5 (showPrice): {price} из {price_text}")
                                        break
                        except Exception as e:
                            logger.debug(f"Ошибка при поиске showPrice: {e}")
                    
                    # Способ 4: Попытка найти в атрибутах data
                    if not price_found:
                        try:
                            # Ищем элемент с атрибутом data-price или data-spm
                            price_data_elements = card.find_elements(By.XPATH, ".//*[@data-price or @data-spm]")
                            for element in price_data_elements:
                                price_data = element.get_attribute('data-price')
                                if price_data:
                                    price = price_data
                                    price_found = True
                                    logger.debug(f"Нашли цену способом 4: {price}")
                                    break
                        except:
                            pass
                    
                    # Последний способ: ищем в тексте всего элемента карточки
                    if not price_found:
                        try:
                            card_text = card.text
                            # Ищем шаблон ¥ с числами после него
                            import re
                            price_matches = re.findall(r'¥\s*(\d+(?:\.\d+)?)', card_text)
                            if price_matches:
                                price = price_matches[0]
                                price_found = True
                                logger.debug(f"Нашли цену способом 5: {price}")
                        except:
                            pass
                    
                    # Сохраняем найденную цену
                    product_data['price'] = price
                    
                    # Логируем если цена не найдена
                    if not price_found or price == "0":
                        logger.warning(f"Не удалось найти цену для товара: {product_data['title']}")
                        # Сохраняем HTML карточки для диагностики
                        try:
                            card_html = card.get_attribute('outerHTML')
                            logger.debug(f"HTML карточки товара с нулевой ценой: {card_html}")
                            
                            # Пытаемся найти все элементы с классом, содержащим price
                            price_elements = card.find_elements(By.XPATH, ".//*[contains(@class, 'price')]")
                            if price_elements:
                                for i, el in enumerate(price_elements):
                                    try:
                                        el_html = el.get_attribute('outerHTML')
                                        el_text = el.text
                                        logger.debug(f"Price element #{i}: HTML={el_html}, Text={el_text}")
                                    except:
                                        pass
                            
                            # Ищем элементы, содержащие символ юаня ¥
                            yuan_elements = card.find_elements(By.XPATH, ".//*[contains(text(), '¥')]")
                            if yuan_elements:
                                for i, el in enumerate(yuan_elements):
                                    try:
                                        el_html = el.get_attribute('outerHTML')
                                        el_text = el.text
                                        logger.debug(f"Yuan element #{i}: HTML={el_html}, Text={el_text}")
                                    except:
                                        pass
                        except Exception as html_err:
                            logger.warning(f"Не удалось получить HTML карточки: {html_err}")
                    
                    processed_products.append(product_data)
                    
                except Exception as e:
                    logger.error(f"Ошибка при обработке карточки товара: {e}")
                    continue
            
            return processed_products
            
        except Exception as e:
            logger.error(f"Ошибка при обработке карточек товаров: {e}")
            return []
            
    def _get_text_or_default(self, element, selector, default=""):
        """
        Безопасное получение текста элемента
        
        :param element: Родительский элемент
        :param selector: CSS селектор
        :param default: Значение по умолчанию
        :return: Текст элемента или значение по умолчанию
        """
        try:
            elements = element.find_elements(By.CSS_SELECTOR, selector)
            if elements and len(elements) > 0:
                return elements[0].text.strip()
            return default
        except:
            return default
            
    def _get_attribute_or_default(self, element, selector, attribute, default=""):
        """
        Безопасное получение атрибута элемента
        
        :param element: Родительский элемент
        :param selector: CSS селектор
        :param attribute: Имя атрибута
        :param default: Значение по умолчанию
        :return: Значение атрибута или значение по умолчанию
        """
        try:
            elements = element.find_elements(By.CSS_SELECTOR, selector)
            if elements and len(elements) > 0:
                value = elements[0].get_attribute(attribute)
                return value if value else default
            return default
        except:
            return default
    
    def _close_popup_windows(self):
        """
        Закрывает различные всплывающие окна на сайте 1688.com
        Оптимизирован для сверхбыстрого выполнения
        """
        try:
            # Экспресс-проверка наличия всплывающего окна блокировки
            try:
                # Максимально быстрая проверка, пропускаем find_element для скорости
                popup = self.driver.execute_script(
                    """
                    var popup = document.querySelector('div[class*="MIDDLEWARE_FRAME"]');
                    return popup && window.getComputedStyle(popup).display !== 'none';
                    """
                )
                
                if popup:
                    # Закрываем окно через JavaScript для максимальной скорости
                    self.driver.execute_script(
                        """
                        // Находим кнопки закрытия и нажимаем без лишних проверок
                        var buttons = document.querySelectorAll('button');
                        for(var i=0; i<buttons.length; i++) {
                            if(buttons[i].innerText.includes('отово') || 
                               buttons[i].innerText.includes('Got') ||
                               buttons[i].innerText.includes('Управ')) {
                                buttons[i].click();
                                break;
                            }
                        }
                        
                        // Пробуем также нажать на любое изображение в окне (часто крестик)
                        var imgs = document.querySelectorAll('.J_MIDDLEWARE_FRAME_WIDGET img');
                        if(imgs.length > 0) imgs[0].click();
                        """
                    )
                    # Минимальная пауза для применения изменений
                    time.sleep(0.1)
            except:
                pass
                
            # Проверяем наличие окна проверки человека (капчи) - минимальная версия
            captcha_container = self.driver.execute_script(
                """
                var captcha = document.querySelector('.J_MIDDLEWARE_FRAME_WIDGET');
                return captcha && window.getComputedStyle(captcha).display !== 'none';
                """
            )
            
            if captcha_container:
                self._handle_captcha()
            
            return True
        except Exception as e:
            logger.warning(f"Ошибка при закрытии всплывающих окон: {e}")
            return False
            
    def _handle_captcha(self):
        """
        Обрабатывает окно проверки человека (капчи) на 1688.com
        """
        try:
            # Проверяем наличие iframe капчи
            captcha_frame = None
            
            # Проверяем наличие элемента J_MIDDLEWARE_FRAME_WIDGET
            try:
                captcha_container = self.driver.find_element(By.CLASS_NAME, "J_MIDDLEWARE_FRAME_WIDGET")
                if captcha_container and captcha_container.is_displayed():
                    logger.warning("Обнаружено окно проверки человека (капча)")
                    
                    # Получаем все iframe на странице
                    iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                    
                    if iframes:
                        # Перебираем все iframe и пытаемся найти тот, который связан с капчей
                        for iframe in iframes:
                            src = iframe.get_attribute("src")
                            if src and "punish" in src:
                                captcha_frame = iframe
                                break
                        
                        if captcha_frame:
                            logger.info("Найден iframe с капчей, пытаемся решить")
                            
                            # Переключаемся на frame капчи
                            self.driver.switch_to.frame(captcha_frame)
                            
                            # Ищем различные типы элементов капчи
                            slider = self.driver.find_element(By.CSS_SELECTOR, ".nc_iconfont.btn_slide")
                            
                            if slider and slider.is_displayed():
                                logger.info("Найден слайдер капчи, выполняем естественное перетаскивание")
                                
                                # Получаем размер элемента и слайдера
                                track_element = self.driver.find_element(By.CSS_SELECTOR, ".nc-lang-cnt")
                                track_width = track_element.size['width']
                                
                                # Создаем цепочку действий
                                action = ActionChains(self.driver)
                                
                                # Нажимаем и удерживаем слайдер
                                action.click_and_hold(slider).perform()
                                
                                # Определяем минимальное количество шагов
                                num_steps = random.randint(5, 8)  # Минимальное количество шагов для высокой скорости
                                
                                # Создаем сверхбыстрый профиль движения
                                total_duration = random.uniform(0.05, 0.08)  # Сверхкороткое время на весь процесс
                                step_time = total_duration / num_steps  # Время на один шаг (минимальное)
                                
                                # Начальное положение
                                current_x = 0
                                
                                # Быстрое и плавное движение с минимальными паузами
                                for i in range(num_steps):
                                    # Линейное движение для максимальной скорости
                                    progress = i / (num_steps - 1)  # От 0 до 1
                                    
                                    # Целевая позиция для текущего шага
                                    target_x = track_width * progress
                                    
                                    # Размер следующего перемещения
                                    move_size = target_x - current_x
                                    
                                    # Перемещаем слайдер на следующую позицию без вариаций
                                    action.move_by_offset(move_size, 0).perform()
                                    current_x += move_size
                                    
                                    # Минимальная микро-пауза
                                    if i < num_steps - 1:  # Пропускаем паузу на последнем шаге
                                        time.sleep(step_time)
                                
                                # Отпускаем слайдер без задержки
                                action.release().perform()
                                
                                # Ждем успешной верификации - минимальное время
                                time.sleep(0.5)
                            else:
                                logger.warning("Слайдер капчи найден, но не отображается")
                            
                            # Возвращаемся к основному содержимому страницы
                            self.driver.switch_to.default_content()
                            
                            # Проверяем, исчезла ли капча - с минимальным временем ожидания
                            try:
                                time.sleep(0.5)  # Сокращаем время ожидания до минимума
                                
                                # Проверяем, все еще видна ли капча
                                if captcha_container.is_displayed():
                                    logger.warning("Капча все еще отображается")
                                    
                                    # Пробуем нажать на крестик для закрытия окна капчи
                                    try:
                                        close_button = self.driver.find_element(By.CSS_SELECTOR, ".J_MIDDLEWARE_FRAME_WIDGET img")
                                        if close_button and close_button.is_displayed():
                                            close_button.click()
                                            logger.info("Нажата кнопка закрытия окна капчи")
                                            time.sleep(0.2)  # Минимальное ожидание
                                    except Exception as e:
                                        logger.warning(f"Ошибка при закрытии окна капчи: {e}")
                                    
                                    # Перезагрузка страницы как последнее средство
                                    logger.info("Перезагружаем страницу для обхода капчи")
                                    self.driver.refresh()
                                    time.sleep(2)  # Сокращаем время ожидания после перезагрузки
                                else:
                                    logger.info("Капча успешно пройдена")
                            except Exception as e:
                                logger.info(f"Не удалось проверить статус окна капчи: {e}")
                    else:
                        logger.warning("iframe для капчи не найден")
                        
                        # Пробуем нажать на крестик для закрытия окна
                        try:
                            close_button = captcha_container.find_element(By.TAG_NAME, "img")
                            if close_button:
                                close_button.click()
                                logger.info("Нажата кнопка закрытия окна проверки")
                                time.sleep(1)
                        except:
                            pass
            except NoSuchElementException:
                # Элемент капчи не найден, ничего не делаем
                pass
                
            return True
        except Exception as e:
            logger.error(f"Ошибка при обработке капчи: {e}")
            
            # В случае ошибки пробуем перезагрузить страницу
            try:
                logger.info("Перезагружаем страницу после ошибки обработки капчи")
                self.driver.refresh()
                time.sleep(5)
            except:
                pass
                
            return False