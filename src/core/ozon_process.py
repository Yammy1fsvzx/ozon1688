import time
import re
import json
import uuid
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from src.utils.logger import logger
from src.utils.utils import extract_weight_and_dimensions, convert_price_to_usd

class OzonProcessor:
    """
    Класс для обработки страницы товара Ozon
    """
    
    def __init__(self, driver, timeout=30):
        """
        Инициализация процессора Ozon
        
        :param driver: Экземпляр драйвера Selenium
        :param timeout: Таймаут ожидания элементов на странице (в секундах)
        """
        self.driver = driver
        self.timeout = timeout
        self.wait = WebDriverWait(driver, timeout)
        logger.debug(f"Инициализация OzonProcessor (timeout={timeout})")
    
    def process_product_page(self):
        """
        Обрабатывает страницу товара Ozon и извлекает данные
        Реализован механизм повторных попыток с перезагрузкой страницы
        
        :return: Словарь с данными о товаре или None, если не удалось
        """
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Обработка страницы товара Ozon (Попытка {attempt}/{max_attempts})")
            try:
                # 1. Ждем загрузки ключевого элемента - названия товара
                logger.debug("Ожидание загрузки названия товара...")
                name_selectors = [
                    "div[data-widget='webProductHeading'] h1",
                    "h1.lz6_28",
                    "h1.tsHeadline550Medium"
                ]
                # Используем WebDriverWait для ожидания появления *любого* из селекторов названия
                # Собираем локаторы
                name_locators = [(By.CSS_SELECTOR, selector) for selector in name_selectors]
                
                # Ждем появления хотя бы одного элемента с названием
                WebDriverWait(self.driver, self.timeout).until(
                    EC.any_of(*[EC.presence_of_element_located(loc) for loc in name_locators])
                )
                logger.debug("Название товара загружено")
                
                # 2. Извлекаем основные данные
                product_id = self._extract_product_id()
                product_name = self._get_product_name()
                current_price = self._get_current_price()
                original_price = self._get_original_price()
                images = self.get_product_images()
                characteristics = self._get_product_characteristics()
                
                # 3. Проверяем, что основные данные были извлечены
                if not product_name or current_price == 0:
                    logger.warning(f"Основные данные (название или цена) не найдены на попытке {attempt}")
                    # Если это последняя попытка, выбрасываем исключение
                    if attempt == max_attempts:
                        raise Exception("Не удалось извлечь основные данные после нескольких попыток.")
                    # Иначе, перезагружаем страницу и пробуем снова
                    logger.info("Перезагрузка страницы...")
                    self.driver.refresh()
                    time.sleep(3) # Даем время на перезагрузку
                    continue # Переходим к следующей попытке
                
                # 4. Обрабатываем извлеченные данные
                weight_and_dimensions = extract_weight_and_dimensions(characteristics)
                price_usd = convert_price_to_usd(current_price, 'RUB')
                
                product_data = {
                    'product_id': product_id,
                    'timestamp': datetime.now().isoformat(),
                    'url': self.driver.current_url,
                    'product_name': product_name,
                    'price_current': current_price,
                    'price_original': original_price,
                    'price_usd': price_usd,
                    'images': images,
                    'characteristics': characteristics,
                    'weight': weight_and_dimensions['weight'],
                    'dimensions': weight_and_dimensions['dimensions']
                }
                
                logger.info("Обработка страницы товара успешно завершена")
                return product_data
                
            except TimeoutException:
                logger.warning(f"Таймаут ожидания загрузки названия товара на попытке {attempt}")
                if attempt == max_attempts:
                    logger.error("Не удалось дождаться загрузки страницы после нескольких попыток.")
                    return None
                logger.info("Перезагрузка страницы...")
                self.driver.refresh()
                time.sleep(3)
                continue
                
            except Exception as e:
                logger.error(f"Ошибка при обработке страницы товара на попытке {attempt}: {e}")
                if attempt == max_attempts:
                    logger.error("Не удалось обработать страницу после нескольких попыток.")
                    return None
                logger.info("Перезагрузка страницы...")
                self.driver.refresh()
                time.sleep(3)
                continue
        
        # Если все попытки не удались
        logger.error("Не удалось обработать страницу товара Ozon после всех попыток.")
        return None
    
    def _extract_product_id(self):
        """
        Извлекает ID товара из URL или со страницы
        
        :return: ID товара или случайный UUID, если ID не найден
        """
        url = self.driver.current_url
        
        # Пытаемся извлечь ID из URL
        pattern = r'/product/([^/]+)'
        match = re.search(pattern, url)
        if match:
            product_id = match.group(1)
            logger.debug(f"ID товара извлечен из URL: {product_id}")
            return product_id
        
        # Если не удалось извлечь из URL, пробуем найти в скрытых данных на странице
        try:
            logger.debug("Поиск ID товара в скриптах на странице")
            # Ищем скрытый элемент с ID товара (часто размещают в JSON-данных)
            script_tags = self.driver.find_elements(By.TAG_NAME, 'script')
            for script in script_tags:
                content = script.get_attribute('innerHTML')
                if 'productId' in content:
                    match = re.search(r'"productId":\s*"?(\d+)"?', content)
                    if match:
                        product_id = match.group(1)
                        logger.debug(f"ID товара найден в скрипте: {product_id}")
                        return product_id
        except Exception as e:
            logger.error(f"Ошибка при извлечении ID товара из скриптов: {e}")
        
        # Если не удалось найти ID товара, генерируем случайный UUID
        uuid_value = str(uuid.uuid4())
        logger.warning(f"ID товара не найден, сгенерирован UUID: {uuid_value}")
        return uuid_value
    
    def _get_product_name(self):
        """
        Получает название товара со страницы
        
        :return: Название товара или пустая строка, если название не найдено
        """
        try:
            # Ищем заголовок товара в разных вариантах селекторов
            selectors = [
                "div[data-widget='webProductHeading'] h1",
                "h1.lz6_28",
                "h1.tsHeadline550Medium"
            ]
            
            logger.debug(f"Поиск названия товара по {len(selectors)} селекторам")
            for selector in selectors:
                try:
                    name_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if name_element:
                        name = name_element.text.strip()
                        logger.debug(f"Название товара найдено по селектору '{selector}'")
                        return name
                except NoSuchElementException:
                    logger.debug(f"Селектор '{selector}' не найден")
                    continue
            
            # Если не нашли по селекторам, пробуем более общий поиск
            logger.debug("Поиск названия товара по тегу h1")
            h1_elements = self.driver.find_elements(By.TAG_NAME, 'h1')
            if h1_elements:
                name = h1_elements[0].text.strip()
                logger.debug(f"Название товара найдено в первом теге h1")
                return name
            
            logger.warning("Название товара не найдено")
            return ""
        except Exception as e:
            logger.error(f"Ошибка при получении названия товара: {e}")
            return ""
    
    def _get_current_price(self):
        """
        Получает текущую цену товара
        
        :return: Текущая цена товара в рублях или 0, если цена не найдена
        """
        try:
            # Ищем текущую цену в разных вариантах селекторов
            selectors = [
                "div[data-widget='webPrice'] span.l5y_28",
                "div[data-widget='webPrice'] span.l5y_28.yl3_28",
                "div[data-widget='webPrice'] div.l1z_28 span.lz_28"
            ]
            
            logger.debug(f"Поиск текущей цены по {len(selectors)} селекторам")
            for selector in selectors:
                try:
                    price_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if price_element:
                        price_text = price_element.text.strip()
                        # Извлекаем только цифры из текста цены
                        price = re.sub(r'[^\d]', '', price_text)
                        price_int = int(price) if price else 0
                        logger.debug(f"Текущая цена найдена по селектору '{selector}': {price_int} ₽")
                        return price_int
                except NoSuchElementException:
                    logger.debug(f"Селектор цены '{selector}' не найден")
                    continue
            
            # Если не нашли, пробуем более общий поиск
            logger.debug("Поиск цены по общему селектору [data-widget='webPrice'] span")
            price_elements = self.driver.find_elements(By.CSS_SELECTOR, "[data-widget='webPrice'] span")
            for element in price_elements:
                price_text = element.text.strip()
                if '₽' in price_text:
                    price = re.sub(r'[^\d]', '', price_text)
                    price_int = int(price) if price else 0
                    logger.debug(f"Текущая цена найдена: {price_int} ₽")
                    return price_int
            
            logger.warning("Текущая цена не найдена")
            return 0
        except Exception as e:
            logger.error(f"Ошибка при получении текущей цены: {e}")
            return 0
    
    def _get_original_price(self):
        """
        Получает оригинальную (зачеркнутую) цену товара
        
        :return: Оригинальная цена товара в рублях или None, если нет зачеркнутой цены
        """
        try:
            # Ищем зачеркнутую цену
            selectors = [
                "div[data-widget='webPrice'] span.yl9_28.lz0_28.yl8_28.y9l_28",
                "div[data-widget='webPrice'] span.yl9_28.y9l_28",
                "div[data-widget='webPrice'] span.yl8_28"
            ]
            
            logger.debug(f"Поиск оригинальной цены по {len(selectors)} селекторам")
            for selector in selectors:
                try:
                    price_element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if price_element:
                        price_text = price_element.text.strip()
                        # Извлекаем только цифры из текста цены
                        price = re.sub(r'[^\d]', '', price_text)
                        price_int = int(price) if price else None
                        if price_int:
                            logger.debug(f"Оригинальная цена найдена по селектору '{selector}': {price_int} ₽")
                        return price_int
                except NoSuchElementException:
                    logger.debug(f"Селектор оригинальной цены '{selector}' не найден")
                    continue
            
            logger.debug("Оригинальная цена не найдена (товар без скидки)")
            return None
        except Exception as e:
            logger.error(f"Ошибка при получении оригинальной цены: {e}")
            return None
    
    def get_product_images(self):
        """
        Получение списка ссылок на изображения товара
        """
        try:
            logger.debug("Поиск изображений товара")
            # Ищем все изображения в галерее
            image_elements = self.driver.find_elements(By.CSS_SELECTOR, "div[data-widget='webGallery'] img")
            
            # Если изображений нет, пробуем другие селекторы
            if not image_elements:
                logger.debug("Изображения не найдены по основному селектору, пробуем альтернативный (.z9j_28)")
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, ".z9j_28")
            
            if not image_elements:
                logger.debug("Изображения не найдены по альтернативному селектору, пробуем ещё один (.k1o_28 img)")
                image_elements = self.driver.find_elements(By.CSS_SELECTOR, ".k1o_28 img")
            
            # Извлекаем атрибуты src
            logger.debug(f"Найдено {len(image_elements)} элементов изображений")
            images = []
            for i, img in enumerate(image_elements):
                src = img.get_attribute('src')
                if src and src.startswith('http') and src not in images and 'video' not in src.lower():
                    # Заменяем миниатюры на полноразмерные изображения
                    if 'wc50' in src:
                        src = src.replace('wc50', 'wc1000')
                        logger.debug(f"Изображение {i+1}: заменена миниатюра на полный размер")
                    images.append(src)
                    logger.debug(f"Добавлено изображение {i+1}: {src[:50]}...")
            
            logger.info(f"Всего найдено {len(images)} уникальных изображений товара")
            return images
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении изображений: {str(e)}")
            return []
    
    def _get_product_characteristics(self):
        """
        Получает характеристики товара
        
        :return: Словарь с характеристиками товара
        """
        characteristics = {}
        
        try:
            logger.info("Получение характеристик товара")
            
            # Прокручиваем страницу к разделу характеристик
            logger.debug("Прокрутка к разделу характеристик")
            self._scroll_to_characteristics()
            
            # Ждем немного, чтобы раздел характеристик загрузился
            logger.debug("Ожидание загрузки раздела характеристик")
            time.sleep(2)
            
            # Ищем все группы характеристик
            logger.debug("Поиск групп характеристик по ID")
            characteristic_groups = self.driver.find_elements(By.CSS_SELECTOR, "div[id='section-characteristics'] dl")
            
            if not characteristic_groups:
                logger.debug("Характеристики не найдены по ID, поиск по заголовку")
                # Если не нашли характеристики по ID, пробуем найти по содержимому
                headers = self.driver.find_elements(By.TAG_NAME, 'h2')
                for header in headers:
                    if 'Характеристики' in header.text:
                        logger.debug(f"Найден заголовок раздела характеристик: '{header.text}'")
                        # Нашли заголовок раздела характеристик, ищем характеристики рядом
                        parent = header.find_element(By.XPATH, '..')
                        characteristic_groups = parent.find_elements(By.CSS_SELECTOR, "dl")
                        logger.debug(f"Найдено {len(characteristic_groups)} групп характеристик")
                        break
            
            # Обрабатываем каждую группу характеристик
            total_chars = 0
            for group_idx, group in enumerate(characteristic_groups):
                logger.debug(f"Обработка группы характеристик {group_idx+1}/{len(characteristic_groups)}")
                # Получаем все термины (названия характеристик) и определения (значения)
                terms = group.find_elements(By.TAG_NAME, 'dt')
                definitions = group.find_elements(By.TAG_NAME, 'dd')
                
                # Если количество терминов и определений совпадает, добавляем их в словарь
                if len(terms) == len(definitions):
                    logger.debug(f"В группе {group_idx+1} найдено {len(terms)} характеристик")
                    for i in range(len(terms)):
                        key = terms[i].text.strip()
                        value = definitions[i].text.strip()
                        if key and value:
                            characteristics[key] = value
                            total_chars += 1
                            logger.debug(f"Характеристика: {key} = {value}")
                else:
                    logger.warning(f"Количество терминов ({len(terms)}) и определений ({len(definitions)}) не совпадает")
            
            logger.info(f"Всего собрано {total_chars} характеристик товара")
        
        except Exception as e:
            logger.error(f"Ошибка при получении характеристик товара: {e}")
        
        return characteristics
    
    def _scroll_to_characteristics(self):
        """
        Прокручивает страницу к разделу характеристик
        """
        try:
            logger.debug("Попытка прокрутки к разделу характеристик по ID")
            # Пробуем найти раздел характеристик по ID
            success = self.driver.execute_script("""
                var element = document.getElementById('section-characteristics');
                if (element) {
                    element.scrollIntoView({behavior: 'smooth', block: 'start'});
                    return true;
                }
                return false;
            """)
            
            if success:
                logger.debug("Успешная прокрутка к разделу характеристик по ID")
            
            # Ждем немного после прокрутки
            time.sleep(1)
            
            # Проверяем, был ли успешный скролл
            visible = self.driver.execute_script("""
                var rect = document.getElementById('section-characteristics')?.getBoundingClientRect();
                return rect && rect.top >= 0 && rect.top <= window.innerHeight;
            """)
            
            if visible:
                logger.debug("Раздел характеристик видим в окне браузера")
            else:
                logger.debug("Раздел характеристик не найден по ID или не виден, пробуем альтернативные методы")
                # Если не удалось прокрутить к элементу, пробуем прокрутить на фиксированное расстояние
                self.driver.execute_script("window.scrollBy(0, 2000);")
                logger.debug("Выполнена прокрутка на 2000 пикселей вниз")
                time.sleep(1)
                
                # Ищем заголовок раздела характеристик и прокручиваем к нему
                headers = self.driver.find_elements(By.TAG_NAME, 'h2')
                for header in headers:
                    if 'Характеристики' in header.text:
                        logger.debug(f"Найден заголовок '{header.text}', прокручиваем к нему")
                        self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", header)
                        time.sleep(1)
                        logger.debug("Выполнена прокрутка к заголовку характеристик")
                        break
        
        except Exception as e:
            logger.error(f"Ошибка при прокрутке к характеристикам: {e}")
            # Если все методы не сработали, просто прокручиваем страницу вниз
            logger.debug("Применяем стандартную прокрутку вниз")
            self.driver.execute_script("window.scrollBy(0, 2000);")
            time.sleep(1) 