import os
import json
from openai import OpenAI
from src.utils.logger import logger

class AIAnalyzer:
    """
    Класс для анализа релевантности товаров с помощью ChatGPT
    """
    
    def __init__(self):
        """
        Инициализация анализатора
        """
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.proxyapi.ru/openai/v1")
        
        if not self.openai_api_key:
            logger.error("API ключ OpenAI не найден. Пожалуйста, добавьте OPENAI_API_KEY в .env файл")
    
    def analyze_relevance(self, ozon_product: dict, alibaba_products: list, threshold: int = 60) -> dict:
        """
        Анализ релевантности товаров с 1688 относительно товара с Ozon
        
        :param ozon_product: Словарь с данными о товаре с Ozon
        :param alibaba_products: Список товаров с 1688
        :param threshold: Порог релевантности (0-100)
        :return: Словарь с самым релевантным товаром или None
        """
        try:
            if not self.openai_api_key:
                logger.error("API ключ OpenAI не настроен")
                return None
            
            logger.info(f"Порог релевантности: {threshold}")
            
            logger.info("Начинаем анализ релевантности товаров...")
            
            # Создаем клиент OpenAI
            client = OpenAI(
                api_key=self.openai_api_key,
                base_url=self.openai_base_url
            )
            
            logger.info("Анализируем товары по релевантности...")
            
            # Создаем промпт для GPT
            prompt = f"""
            Ты опытный эксперт по сравнению товаров с маркетплейсов, специализирующийся на китайских товарах. 
            Тебе предстоит проанализировать, насколько товары с китайского маркетплейса 1688 соответствуют товару с российского маркетплейса Ozon.

            Вот информация о товаре с Ozon:
            - Название: {ozon_product.get('title', 'Нет данных')}
            - Характеристики: {ozon_product.get('characteristics', 'Нет данных')}
            - Изображения: {ozon_product.get('images', [])}

            Вот список товаров с 1688 для сравнения:
            {json.dumps([{
                'title': p.get('title', 'Нет данных'),
                'image_url': p.get('image_url', 'Нет данных')
            } for p in alibaba_products], ensure_ascii=False, indent=2)}

            ВАЖНО! При анализе учитывай следующие особенности:
            1. Переводы с китайского часто неточны и могут отличаться от оригинального названия
            2. Ключевые характеристики товара важнее точного совпадения названий
            3. Функциональное назначение товара должно совпадать, даже если названия различаются
            4. Обращай внимание на технические параметры и спецификации, а не только на названия
            5. Визуальное сравнение изображений товаров - важный критерий релевантности
            6. Учитывай возможные различия в качестве фотографий и ракурсах съемки

            Критерии релевантности:
            1. Функциональное соответствие:
               - Товары должны выполнять одну и ту же функцию
               - Технические характеристики должны быть совместимы
               - Размеры и параметры должны соответствовать

            2. Визуальное соответствие:
               - Внешний вид товаров должен быть идентичным
               - Материалы и конструкция должны совпадать
               - Цветовая гамма и дизайн должны соответствовать
               - Форма и размеры должны совпадать
               - Детали и элементы должны быть одинаковыми

            3. Целевое назначение:
               - Товары должны быть предназначены для одной и той же цели
               - Целевая аудитория должна совпадать
               - Условия использования должны быть одинаковыми

            Оцени общую релевантность от 0 до 100, где:
            - 0-30: Разные товары, не соответствуют друг другу
            - 31-60: Похожие товары, но есть существенные различия
            - 61-80: Очень похожие товары с небольшими отличиями
            - 81-100: Идентичные товары по функционалу и характеристикам

            Важно:
            - Не занижай оценку только из-за различий в переводах названий
            - Основной фокус на функциональном соответствии и характеристиках
            - Учитывай возможные неточности в переводах с китайского
            - Обращай внимание на технические параметры и спецификации
            - При сравнении изображений учитывай возможные различия в качестве фото

            Ответ дай в формате JSON: 
            {{"results": [
                {{"relevance_score": число от 0 до 100, 
                  "explanation": "краткое объяснение оценки", 
                  "product_index": индекс товара в списке (начиная с 0)}}
                для каждого товара
            ]}}
            
            Важно: верни ТОЛЬКО JSON без дополнительного текста.
            """
            
            # Отправляем запрос к API
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Ты эксперт по сравнению товаров, отвечаешь только в JSON формате."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            # Получаем ответ
            analysis_text = response.choices[0].message.content
            logger.info(f"Получен ответ от OpenAI: {analysis_text}")
            # Парсим JSON-ответ
            analysis_results = json.loads(analysis_text)
            
            # Обрабатываем результат анализа
            if isinstance(analysis_results, dict) and 'results' in analysis_results:
                results = analysis_results['results']
                # Фильтруем товары с оценкой выше порога (60)
                relevant_products = [p for p in results if p.get('relevance_score', 0) > threshold]
                
                if relevant_products:
                    # Выбираем товар с максимальной оценкой
                    best_product = max(relevant_products, key=lambda x: x.get('relevance_score', 0))
                    logger.info(f"Найден релевантный товар с оценкой {best_product.get('relevance_score', 0)}")
                    return best_product
            
            logger.info("Релевантные товары не найдены (нет товаров с оценкой выше 60)")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при анализе релевантности: {e}")
            return None 

    def extract_brand(self, product_title: str) -> str:
        """
        Извлечение бренда из названия товара
        
        :param product_title: Название товара
        :return: Название бренда или пустая строка
        """
        try:
            if not self.openai_api_key:
                logger.error("API ключ OpenAI не настроен")
                return ""
            
            prompt = f"""
            Извлеки название бренда из названия товара. Если бренд не определен, верни пустую строку.
            
            Название товара: {product_title}
            
            Важно:
            - Верни ТОЛЬКО название бренда без дополнительного текста
            - Если бренд не определен, верни пустую строку
            - Не добавляй никаких пояснений
            """
            
            client = OpenAI(
                api_key=self.openai_api_key,
                base_url=self.openai_base_url
            )
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Ты эксперт по определению брендов, отвечаешь только названием бренда или пустой строкой."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            
            brand = response.choices[0].message.content.strip()
            logger.info(f"Извлечен бренд: {brand}")
            return brand
            
        except Exception as e:
            logger.error(f"Ошибка при извлечении бренда: {e}")
            return "" 