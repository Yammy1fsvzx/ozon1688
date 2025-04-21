import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import undetected_chromedriver as uc
from src.utils.logger import logger

class BrowserManager:
    """
    Класс для управления браузером с использованием Selenium и undetected_chromedriver
    """
    
    def __init__(self, headless=False, timeout=30):
        """
        Инициализация менеджера браузера
        
        :param headless: Запускать браузер в фоновом режиме (без интерфейса)
        :param timeout: Таймаут ожидания элементов на странице (в секундах)
        """
        self.driver = None
        self.headless = headless
        self.timeout = timeout
        self.ozon_domain_pattern = re.compile(r'(^|\.)ozon\.ru$')
        logger.debug(f"Инициализация BrowserManager (headless={headless}, timeout={timeout})")
    
    def open_browser(self):
        """
        Открывает браузер Chrome с необходимыми настройками
        
        :return: Экземпляр WebDriver
        """
        try:
            logger.info("Открываем браузер...")
            
            chrome_options = uc.ChromeOptions()
            
            if self.headless:
                chrome_options.add_argument('--headless')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
            else:
                # Настройки для обычного режима
                chrome_options.add_argument('--window-size=1920,1080')  # Стандартное разрешение
                chrome_options.add_argument('--disable-gpu')  # Отключаем GPU для лучшей производительности
            
            # Добавляем аргументы для работы с изображениями и всплывающими окнами
            chrome_options.add_argument('--disable-popup-blocking')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--allow-file-access-from-files')
            chrome_options.add_argument('--allow-file-access')
            
            # Настройка политики содержимого для разрешения всплывающих окон
            chrome_options.add_argument('--disable-site-isolation-trials')
            
            # Используем экспериментальные опции
            chrome_prefs = {
                "profile.default_content_setting_values.notifications": 1,  # 1=разрешить, 2=блокировать
                "profile.default_content_setting_values.popups": 1,  # 1=разрешить, 2=блокировать
                "profile.default_content_settings.popups": 1,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", chrome_prefs)
            
            # Создаем драйвер с указанными опциями
            driver = uc.Chrome(options=chrome_options)
            
            # Устанавливаем размер окна браузера
            driver.set_window_size(1920, 1080)  # Стандартное разрешение
            
            # Устанавливаем таймаут загрузки страницы
            driver.set_page_load_timeout(60)
            
            # Настраиваем JavaScript для разрешения всплывающих окон
            setup_script = """
            // Разрешаем всплывающие окна
            window.original_open = window.open;
            window.open = function() {
                return window.original_open.apply(this, arguments);
            };
            // Разрешаем уведомления
            if (navigator.permissions) {
                navigator.permissions.query({name: 'notifications'}).then(function(permission) {
                    if (permission.state === 'prompt' || permission.state === 'denied') {
                        console.log('Allowing notifications');
                    }
                });
            }
            """
            driver.execute_script(setup_script)
            
            logger.info("Браузер успешно открыт")
            
            self.driver = driver
            return driver
            
        except Exception as e:
            logger.error(f"Ошибка при открытии браузера: {e}")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None
            raise e
    
    def navigate_to_url(self, url):
        """
        Переходит по указанному URL
        
        :param url: URL страницы для перехода
        """
        if not self.driver:
            logger.error("Браузер не инициализирован")
            raise Exception("Браузер не инициализирован. Сначала вызовите метод open_browser()")
        
        logger.debug(f"Переход по URL: {url}")
        self.driver.get(url)
        logger.debug("Ожидание полной загрузки страницы")
        time.sleep(3)  # Даем странице полностью загрузиться
        
        # Проверка наличия капчи или блокировки на странице 1688.com
        if "1688.com" in url:
            self.check_and_handle_captcha()
            
        logger.debug(f"Страница загружена: {self.driver.title}")
    
    def check_and_handle_captcha(self):
        """
        Проверяет наличие капчи на странице 1688.com и пытается её решить
        с использованием естественного движения ползунка
        """
        try:
            # Проверяем наличие элемента капчи
            captcha_container = self.driver.find_elements(By.CLASS_NAME, "J_MIDDLEWARE_FRAME_WIDGET")
            
            if captcha_container and captcha_container[0].is_displayed():
                logger.warning("Обнаружено окно проверки человека (капча) при загрузке страницы")
                
                # Получаем все iframe на странице
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                
                if iframes:
                    # Перебираем все iframe и пытаемся найти тот, который связан с капчей
                    for iframe in iframes:
                        src = iframe.get_attribute("src")
                        if src and "punish" in src:
                            logger.info("Найден iframe с капчей, пытаемся решить")
                            
                            # Переключаемся на frame капчи
                            self.driver.switch_to.frame(iframe)
                            
                            # Ищем слайдер или другие элементы капчи
                            try:
                                # Ищем различные типы элементов капчи
                                from selenium.webdriver.common.action_chains import ActionChains
                                import random
                                import time
                                
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
                                    
                                    logger.info("Выполнено быстрое перетаскивание слайдера")
                                    
                                    # Ждем успешной верификации минимальное время
                                    time.sleep(0.5)
                            except Exception as slider_error:
                                logger.info(f"Слайдер капчи не найден или произошла ошибка: {slider_error}")
                                
                                # Пытаемся найти кнопку для решения капчи
                                try:
                                    # Ищем кнопки или элементы для взаимодействия
                                    buttons = self.driver.find_elements(By.TAG_NAME, "button")
                                    for button in buttons:
                                        if button.is_displayed():
                                            button.click()
                                            logger.info("Нажата кнопка в форме капчи")
                                            time.sleep(0.3)  # Минимальное время ожидания
                                            break
                                except Exception as button_error:
                                    logger.warning(f"Не удалось найти кнопки в форме капчи: {button_error}")
                            
                            # Возвращаемся к основному содержимому страницы
                            self.driver.switch_to.default_content()
                            break
                
                # Проверяем, исчезла ли капча после попытки решения - сокращаем время проверки
                try:
                    time.sleep(0.5)  # Минимальное время на обработку капчи
                    
                    # Проверяем, все еще видна ли капча
                    captcha_container = self.driver.find_elements(By.CLASS_NAME, "J_MIDDLEWARE_FRAME_WIDGET")
                    if captcha_container and captcha_container[0].is_displayed():
                        logger.warning("Капча все еще отображается, пробуем закрыть или перезагрузить страницу")
                        
                        # Пробуем нажать на крестик для закрытия окна
                        try:
                            close_button = self.driver.find_element(By.CSS_SELECTOR, ".J_MIDDLEWARE_FRAME_WIDGET img")
                            if close_button and close_button.is_displayed():
                                close_button.click()
                                logger.info("Нажата кнопка закрытия окна капчи")
                                time.sleep(1)
                        except Exception as close_error:
                            logger.warning(f"Не удалось закрыть окно капчи: {close_error}")
                        
                        # Если капча все еще отображается, перезагружаем страницу
                        captcha_container = self.driver.find_elements(By.CLASS_NAME, "J_MIDDLEWARE_FRAME_WIDGET")
                        if captcha_container and captcha_container[0].is_displayed():
                            logger.info("Перезагружаем страницу для обхода капчи")
                            self.driver.refresh()
                            time.sleep(5)
                    else:
                        logger.info("Капча успешно обработана")
                except Exception as check_error:
                    logger.warning(f"Ошибка при проверке состояния капчи: {check_error}")
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при обработке капчи: {e}")
            return False
    
    def is_ozon_url(self, url):
        """
        Проверяет, что URL относится к сайту Ozon
        
        :param url: URL для проверки
        :return: True, если URL ведет на Ozon, иначе False
        """
        logger.debug(f"Проверка URL на принадлежность к Ozon: {url}")
        
        # Проверка на короткую или полную ссылку Ozon
        if 'ozon.ru' in url:
            logger.debug("URL содержит домен ozon.ru")
            return True
        elif 'oz.by' in url:  # Белорусская версия Ozon
            logger.debug("URL содержит домен oz.by (белорусская версия Ozon)")
            return True
        
        # Проверка на сокращенные ссылки Ozon
        ozon_short_urls = ['vk.cc', 'goo.gl', 'bit.ly', 't.co']
        for short_url in ozon_short_urls:
            if short_url in url:
                logger.debug(f"Обнаружена сокращенная ссылка: {short_url}")
                # Для коротких ссылок нужно перейти по ним и проверить конечный URL
                try:
                    logger.debug("Открываем временный браузер для проверки перенаправления")
                    temp_driver = webdriver.Chrome()
                    temp_driver.get(url)
                    final_url = temp_driver.current_url
                    temp_driver.quit()
                    logger.debug(f"Конечный URL после перенаправления: {final_url}")
                    return self.is_ozon_url(final_url)
                except Exception as e:
                    logger.error(f"Ошибка при проверке сокращенной ссылки: {e}")
                    return False
        
        logger.debug("URL не относится к Ozon")
        return False
    
    def get_windows_info(self):
        """
        Получает информацию обо всех открытых окнах браузера
        
        :return: Словарь с информацией об окнах {window_handle: {'title': title, 'url': url}}
        """
        if not self.driver:
            logger.error("Браузер не инициализирован")
            raise Exception("Браузер не инициализирован. Сначала вызовите метод open_browser()")
        
        logger.debug("Получение информации обо всех открытых окнах")
        windows_info = {}
        current_handle = self.driver.current_window_handle
        
        # Итерация по всем открытым окнам
        for handle in self.driver.window_handles:
            logger.debug(f"Переключение на окно с handle: {handle}")
            self.driver.switch_to.window(handle)
            windows_info[handle] = {
                'title': self.driver.title,
                'url': self.driver.current_url
            }
            logger.debug(f"Окно {handle}: {self.driver.title}")
        
        # Возвращаемся к исходному окну
        logger.debug(f"Возвращение к исходному окну: {current_handle}")
        self.driver.switch_to.window(current_handle)
        
        return windows_info
    
    def scroll_to_element(self, element_id=None, selector=None, scroll_amount=None):
        """
        Прокручивает страницу к указанному элементу или на указанное количество пикселей
        
        :param element_id: ID элемента, к которому нужно прокрутить
        :param selector: CSS-селектор элемента, к которому нужно прокрутить
        :param scroll_amount: Количество пикселей для прокрутки
        """
        if not self.driver:
            logger.error("Браузер не инициализирован")
            raise Exception("Браузер не инициализирован. Сначала вызовите метод open_browser()")
        
        # Прокрутка к элементу по ID
        if element_id:
            logger.debug(f"Попытка прокрутки к элементу с ID: {element_id}")
            try:
                element = self.driver.find_element(By.ID, element_id)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                # Немного прокручиваем вверх, чтобы элемент не был под шапкой сайта
                self.driver.execute_script("window.scrollBy(0, -120);")
                logger.debug(f"Успешная прокрутка к элементу с ID: {element_id}")
                return True
            except NoSuchElementException:
                logger.warning(f"Элемент с ID '{element_id}' не найден. Пробуем альтернативные методы прокрутки.")
        
        # Прокрутка к элементу по селектору
        if selector:
            logger.debug(f"Попытка прокрутки к элементу с селектором: {selector}")
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                self.driver.execute_script("window.scrollBy(0, -120);")
                logger.debug(f"Успешная прокрутка к элементу с селектором: {selector}")
                return True
            except NoSuchElementException:
                logger.warning(f"Элемент с селектором '{selector}' не найден. Пробуем альтернативные методы прокрутки.")
        
        # Прокрутка на указанное количество пикселей
        if scroll_amount:
            logger.debug(f"Прокрутка на {scroll_amount} пикселей")
            self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
            return True
        
        # Если не указан ни один параметр или не удалось прокрутить к элементу,
        # просто прокручиваем страницу вниз на 2000 пикселей
        logger.debug("Применяем стандартную прокрутку на 2000 пикселей")
        self.driver.execute_script("window.scrollBy(0, 2000);")
        return True
    
    def close_browser(self):
        """
        Закрывает браузер и освобождает ресурсы
        """
        if self.driver:
            try:
                logger.info("Закрываем браузер...")
                
                # Закрываем все окна браузера
                try:
                    for handle in self.driver.window_handles:
                        self.driver.switch_to.window(handle)
                        self.driver.close()
                except Exception as window_error:
                    logger.warning(f"Ошибка при закрытии окон браузера: {window_error}")
                
                # Закрываем драйвер
                try:
                    self.driver.quit()
                except Exception as quit_error:
                    logger.warning(f"Ошибка при закрытии драйвера: {quit_error}")
                    # Пробуем альтернативный способ закрытия
                    try:
                        self.driver.close()
                    except:
                        pass
                
                logger.info("Браузер успешно закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии браузера: {e}")
            finally:
                self.driver = None
                
    def restart_browser(self, startup_url=None):
        """
        Перезапускает браузер и возвращает новый экземпляр WebDriver
        
        :param startup_url: URL для перехода после запуска браузера (опционально)
        :return: Новый экземпляр WebDriver
        """
        logger.info("Перезапуск браузера...")
        
        # Закрываем текущий браузер, если он открыт
        self.close_browser()
        
        # Открываем новый браузер
        driver = self.open_browser()
        
        # Если указан URL, переходим по нему
        if startup_url:
            try:
                logger.info(f"Переход по URL после перезапуска: {startup_url}")
                self.navigate_to_url(startup_url)
            except Exception as e:
                logger.error(f"Ошибка при переходе по URL после перезапуска: {e}")
                
        return driver 