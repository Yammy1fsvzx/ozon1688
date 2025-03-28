#!/usr/bin/env python
# -*- coding: utf-8 -*-

from src.core.database import Database
from src.core.models import MatchedProduct, ProductProfitability
from src.utils.logger import logger

def recalculate_all_profitability():
    """
    Перерасчет маржинальности для всех товаров с учетом корректного веса в граммах
    """
    db = Database()
    session = db.get_session()
    
    try:
        # Получаем все ID сопоставлений
        match_ids = [match[0] for match in session.query(MatchedProduct.id).all()]
        total_matches = len(match_ids)
        logger.info(f"Найдено {total_matches} сопоставлений для перерасчета")
        
        # Удаляем все старые записи о маржинальности
        session.query(ProductProfitability).delete()
        session.commit()
        logger.info("Старые записи о маржинальности удалены")
        
        # Закрываем сессию после удаления старых записей
        session.close()
        
        # Перерасчитываем маржинальность для каждого сопоставления
        success_count = 0
        error_count = 0
        
        for i, match_id in enumerate(match_ids, 1):
            try:
                logger.info(f"Обработка сопоставления {i}/{total_matches} (ID: {match_id})")
                if db.calculate_profitability(match_id):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Ошибка при перерасчете маржинальности для ID {match_id}: {e}")
                error_count += 1
        
        logger.info(f"Перерасчет завершен. Успешно: {success_count}, Ошибок: {error_count}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при перерасчете маржинальности: {e}")
        return False

if __name__ == "__main__":
    logger.info("Запуск перерасчета маржинальности...")
    recalculate_all_profitability() 