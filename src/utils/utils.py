import re
import logging

logger = logging.getLogger(__name__)

def extract_weight_and_dimensions(characteristics: dict) -> dict:
    """
    Извлекает вес и габариты из характеристик товара.
    
    :param characteristics: Словарь характеристик товара
    :return: Словарь с весом и габаритами
    """
    weight = None
    dimensions = None
    
    # Поиск веса
    if 'Вес товара, г' in characteristics:
        weight_str = characteristics['Вес товара, г']
        try:
            weight = float(weight_str)  # Преобразуем в число с плавающей точкой
        except ValueError:
            logger.error(f"Не удалось преобразовать вес: {weight_str}")
            weight = None  # Устанавливаем в None, если преобразование не удалось

    # Поиск габаритов
    if 'Размеры, мм' in characteristics:
        dimensions_str = characteristics['Размеры, мм']
        dimensions = dimensions_str  # Сохраняем размеры как есть
    
    return {
        'weight': weight,
        'dimensions': dimensions
    }

def convert_price_to_usd(price_value, currency=None):
    """
    Универсальная функция для конвертации цен в доллары США (USD).
    Автоматически определяет валюту или использует указанную.
    
    :param price_value: Цена в виде числа или строки (может содержать символы валюты)
    :param currency: Валюта (если известна): 'RUB', 'CNY' или None для автоопределения
    :return: Цена в долларах США (USD)
    """
    # Константы курсов валют
    RUB_TO_USD_RATE = 85.0  # 1 USD = 85 RUB
    CNY_TO_USD_RATE = 7.14  # 1 USD = 7.14 CNY
    
    # Логируем входные данные для отладки
    logger.debug(f"Конвертация цены: {price_value}, валюта: {currency or 'не указана'}")
    
    # Обработка None и пустых значений
    if price_value is None:
        logger.warning("Получено пустое значение цены (None)")
        return 0.0
    
    # Если price_value - число, используем его напрямую
    if isinstance(price_value, (int, float)):
        price_num = float(price_value)
        
        # Если валюта указана явно, используем ее
        if currency:
            currency_upper = currency.upper()
            if currency_upper == 'RUB':
                result = round(price_num / RUB_TO_USD_RATE, 2)
                logger.debug(f"Числовое значение {price_num} RUB -> {result} USD")
                return result
            elif currency_upper == 'CNY':
                result = round(price_num / CNY_TO_USD_RATE, 2)
                logger.debug(f"Числовое значение {price_num} CNY -> {result} USD")
                return result
            else:
                logger.warning(f"Неизвестная валюта: {currency}, используем CNY по умолчанию")
                result = round(price_num / CNY_TO_USD_RATE, 2)
                logger.debug(f"Числовое значение {price_num} CNY (по умолчанию) -> {result} USD")
                return result
        else:
            # Если валюта не указана, по умолчанию считаем, что это CNY
            result = round(price_num / CNY_TO_USD_RATE, 2)
            logger.debug(f"Числовое значение {price_num} CNY (по умолчанию) -> {result} USD")
            return result
    
    # Обработка пустых строк
    price_str = str(price_value).strip()
    if not price_str:
        logger.warning("Получена пустая строка цены")
        return 0.0
    
    # Определяем валюту по символам в строке
    detected_currency = None
    
    # Расширенный список маркеров валют
    if any(marker in price_str.lower() for marker in ['руб', '₽', 'rub', 'р.', 'р ']):
        detected_currency = 'RUB'
    elif any(marker in price_str for marker in ['¥', 'cny', '元', 'юан', 'yuan']):
        detected_currency = 'CNY'
    elif any(marker in price_str for marker in ['$', 'usd', 'долл']):
        # Если уже в долларах, просто извлекаем число
        detected_currency = 'USD'
    else:
        # Если валюта не определена автоматически и не передана явно, 
        # используем логику выбора по умолчанию
        if currency:
            detected_currency = currency.upper()
            logger.debug(f"Используем явно указанную валюту: {detected_currency}")
        else:
            # По умолчанию предполагаем CNY для Alibaba и RUB для Ozon
            detected_currency = 'CNY'
            logger.debug(f"Валюта не определена, используем CNY по умолчанию")
    
    # Извлекаем число из строки с улучшенным алгоритмом
    # Шаг 1: Удаляем все нецифровые символы кроме точек и запятых
    price_clean = ''.join(c for c in price_str if c.isdigit() or c in '.,')
    
    # Шаг 2: Заменяем запятые на точки
    price_clean = price_clean.replace(',', '.')
    
    # Шаг 3: Если в строке несколько точек, оставляем только последнюю
    if price_clean.count('.') > 1:
        parts = price_clean.split('.')
        price_clean = ''.join(parts[:-1]) + '.' + parts[-1]
    
    # Шаг 4: Преобразуем в число
    try:
        price_num = float(price_clean)
    except ValueError:
        logger.error(f"Не удалось преобразовать строку '{price_str}' в число")
        return 0.0
    
    # Конвертируем в USD в зависимости от определенной валюты
    if detected_currency == 'RUB':
        result = round(price_num / RUB_TO_USD_RATE, 2)
        logger.debug(f"Строковое значение {price_num} RUB -> {result} USD")
        return result
    elif detected_currency == 'USD':
        logger.debug(f"Цена уже в USD: {price_num}")
        return round(price_num, 2)
    else:  # CNY по умолчанию
        result = round(price_num / CNY_TO_USD_RATE, 2)
        logger.debug(f"Строковое значение {price_num} CNY -> {result} USD")
        return result