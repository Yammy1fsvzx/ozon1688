#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import argparse
import os
import multiprocessing
from dotenv import load_dotenv
from src.bot.telegram_bot import TelegramBot
from src.core.task_processor import TaskProcessor
from src.utils.logger import setup_logger, logger
from src.core.database import Database
from src.core.browser_manager import BrowserManager

def parse_arguments():
    """
    Парсинг аргументов командной строки
    """
    parser = argparse.ArgumentParser(description='Парсер товаров Ozon')
    parser.add_argument('--headless', action='store_true', help='Запуск в фоновом режиме')
    parser.add_argument('--debug', action='store_true', help='Включить отладочный режим')
    parser.add_argument('--no-logs', action='store_true', help='Не сохранять логи в файл')
    return parser.parse_args()

def run_processor(headless: bool, debug: bool, save_logs: bool):
    """
    Функция для запуска процессора в отдельном процессе
    
    :param headless: Запускать браузер в фоновом режиме
    :param debug: Включить отладочный режим логирования
    :param save_logs: Сохранять логи в файл
    """
    # Не настраиваем логгер заново, т.к. он уже настроен в родительском процессе
    # Создаем экземпляры необходимых классов
    db = Database()
    browser_manager = BrowserManager(headless=headless)
    
    # Правильно инициализируем TaskProcessor с нужными параметрами
    processor = TaskProcessor(db=db, browser_manager=browser_manager)
    asyncio.run(processor.start())

def run_bot(bot_token: str, debug: bool, save_logs: bool):
    """
    Функция для запуска бота в отдельном процессе
    
    :param bot_token: Токен Telegram бота
    :param debug: Включить отладочный режим логирования
    :param save_logs: Сохранять логи в файл
    """
    # Не настраиваем логгер заново, т.к. он уже настроен в родительском процессе
    bot = TelegramBot(bot_token)
    asyncio.run(bot.start())

def main():
    """
    Основная функция
    """
    # Выводим логотип при старте
    print("""
⣾⣿⠿⠿⠶⠿⢿⣿⣿⣿⣿⣦⣤⣄⢀⡅⢠⣾⣛⡉⠄⠄⠄⠸⢀⣿⠄
⢀⡋⣡⣴⣶⣶⡀⠄⠄⠙⢿⣿⣿⣿⣿⣿⣴⣿⣿⣿⢃⣤⣄⣀⣥⣿⣿⠄
⢸⣇⠻⣿⣿⣿⣧⣀⢀⣠⡌⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠿⠿⣿⣿⣿⠄
⢸⣿⣷⣤⣤⣤⣬⣙⣛⢿⣿⣿⣿⣿⣿⣿⡿⣿⣿⡍⠄⠄⢀⣤⣄⠉⠋⣰
⣖⣿⣿⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⣿⢇⣿⣿⡷⠶⠶⢿⣿⣿⠇⢀⣤
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⣿⣿⣿⡇⣿⣿⣿⣿⣿⣿⣷⣶⣥⣴⣿⡗
⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠄
⣦⣌⣛⣻⣿⣿⣧⠙⠛⠛⡭⠅⠒⠦⠭⣭⡻⣿⣿⣿⣿⣿⣿⣿⣿⡿⠃⠄
⣿⣿⣿⣿⣿⣿⣿⡆⠄⠄⠄⠄⠄⠄⠄⠄⠹⠈⢋⣽⣿⣿⣿⣿⣵⣾⠃⠄
⣿⣿⣿⣿⣿⣿⣿⣿⠄⣴⣿⣶⣄⠄⣴⣶⠄⢀⣾⣿⣿⣿⣿⣿⣿⠃⠄⠄
⠈⠻⣿⣿⣿⣿⣿⣿⡄⢻⣿⣿⣿⠄⣿⣿⡀⣾⣿⣿⣿⣿⣛⠛⠁⠄⠄⠄
⠄⠄⠈⠛⢿⣿⣿⣿⠁⠞⢿⣿⣿⡄⢿⣿⡇⣸⣿⣿⠿⠛⠁⠄⠄⠄⠄⠄
⠄⠄⠄⠄⠄⠉⠻⣿⣿⣾⣦⡙⠻⣷⣾⣿⠃⠿⠋⠁⠄⠄⠄⠄⠄⢀⣠⣴
⣿⣶⣶⣮⣥⣒⠲⢮⣝⡿⣿⣿⡆⣿⡿⠃⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄⠄
    """)
    print("\n" + "-"*50 + "\n") # Добавим разделитель

    # Парсим аргументы
    args = parse_arguments()
    
    # Настраиваем логирование единожды в главном процессе
    # Этот логгер будет единственным для всего приложения
    setup_logger(debug=args.debug, save_logs=not args.no_logs)
    logger.info("🚀 Запуск Ozon1688")
    
    # Загружаем переменные окружения из .env файла
    load_dotenv()
    
    # Получаем токен бота из переменной окружения
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        logger.error("❌ Не указан токен бота (TELEGRAM_BOT_TOKEN)")
        return
    
    try:
        # Создаем процессы для бота и процессора, передаем параметры логирования
        bot_process = multiprocessing.Process(
            target=run_bot,
            args=(bot_token, args.debug, not args.no_logs)
        )
        
        processor_process = multiprocessing.Process(
            target=run_processor,
            args=(args.headless, args.debug, not args.no_logs)
        )
        
        # Запускаем процессы
        bot_process.start()
        processor_process.start()
        
        logger.info("⏳ Процесс инициализации...")
        
        # Ждем завершения процессов
        bot_process.join()
        processor_process.join()
        
    except KeyboardInterrupt:
        logger.warning("⚠️  Получен сигнал завершения работы")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {str(e)}")
    finally:
        # Останавливаем процессы
        if 'bot_process' in locals() and bot_process.is_alive():
            bot_process.terminate()
        if 'processor_process' in locals() and processor_process.is_alive():
            processor_process.terminate()
        logger.info("👋 Завершение работы")

if __name__ == "__main__":
    main()