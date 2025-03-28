#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from datetime import datetime
from loguru import logger

# Флаг, показывающий, был ли логгер уже инициализирован
_logger_initialized = False

def setup_logger(debug: bool = False, save_logs: bool = True):
    """
    Настройка логгера. Если логгер уже был инициализирован, 
    функция просто возвращает существующий экземпляр.
    
    :param debug: Включить отладочный режим
    :param save_logs: Сохранять логи в файл
    :return: Объект логгера
    """
    global _logger_initialized
    
    # Проверяем, был ли логгер уже инициализирован
    if _logger_initialized:
        logger.debug("Логгер уже инициализирован, пропускаем настройку")
        return logger
    
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Добавляем вывод в консоль
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if debug else "INFO"
    )
    
    if save_logs:
        # Создаем директорию для логов, если её нет
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Файлы логов с использованием даты в имени файла
        main_log_file = os.path.join(log_dir, "ozon1688_app.log")
        
        # Добавляем файловый обработчик для общих логов
        # Используем rotation с указанием размера и ротацией по дням
        logger.add(
            main_log_file,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG" if debug else "INFO",
            rotation="50 MB",                # Ротация по размеру (50 МБ)
            compression="zip",               # Сжатие старых логов
            retention=10,                    # Хранить только 10 последних файлов
            enqueue=True,                    # Асинхронная запись для повышения производительности
            backtrace=True                   # Включить полный стек-трейс для исключений
        )
    
    # Настраиваем отдельный файл для ошибок
    error_log_file = os.path.join(log_dir, "ozon1688_error.log") if os.path.exists(log_dir) else "ozon1688_error.log"
    
    logger.add(
        error_log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="10 MB",                    # Ротация по размеру (10 МБ)
        compression="zip",                   # Сжатие старых логов
        retention=10,                        # Хранить только 10 последних файлов
        enqueue=True,                        # Асинхронная запись
        backtrace=True,                      # Включить полный стек-трейс для исключений
        diagnose=True                        # Добавить диагностическую информацию
    )
    
    # Помечаем логгер как инициализированный
    _logger_initialized = True
    
    return logger

# Инициализация логгера с настройками по умолчанию
logger = setup_logger() 