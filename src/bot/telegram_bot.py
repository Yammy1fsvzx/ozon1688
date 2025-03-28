import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.types import FSInputFile
from src.core.database import Database
from src.utils.logger import logger
from src.bot.keyboards import get_reprocess_keyboard, get_main_keyboard
from src.utils.excel_generator import ExcelGenerator
import os

class TelegramBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.db = Database()
        self.excel_generator = ExcelGenerator()
        self.last_report_request = {}  # Словарь для отслеживания времени последнего запроса отчета
        self.last_stats_request = {}   # Словарь для отслеживания времени последнего запроса статистики
        self.last_help_request = {}    # Словарь для отслеживания времени последнего запроса помощи
        self.last_active_request = {}  # Словарь для отслеживания времени последнего запроса активных задач
        
        # Регистрируем обработчики
        self.dp.message.register(self.start_command, Command("start"))
        self.dp.message.register(self.handle_url, lambda msg: not msg.text.startswith('/'))
        self.dp.callback_query.register(self.handle_callback, lambda c: c.data.startswith('reprocess:'))
        self.dp.callback_query.register(self.handle_action_callback, lambda c: c.data.startswith('action:'))
    
    async def start_command(self, message: Message):
        """
        Обработчик команды /start
        """
        welcome_text = (
            "👋 Привет! Я бот для анализа товаров Ozon и поиска аналогов на 1688.com\n\n"
            "🎯 Что я умею:\n"
            "• Парсинг товаров с Ozon\n"
            "• Поиск аналогов на 1688.com\n"
            "• Расчет прибыльности с учетом всех расходов\n"
            "• Генерация отчетов в Excel\n"
            "• Отслеживание статуса обработки\n\n"
            "📝 Как использовать:\n"
            "1. Отправьте мне ссылку на товар с Ozon\n"
            "2. Я добавлю его в очередь на обработку\n"
            "3. После обработки вы получите информацию о найденных аналогах\n\n"
            "🔍 Используйте кнопки ниже для навигации:"
        )
        await message.answer(welcome_text, reply_markup=get_main_keyboard())

    async def handle_action_callback(self, callback: CallbackQuery):
        """
        Обработчик callback-запросов от inline-кнопок главного меню
        """
        _, action = callback.data.split(':')
        
        if action == 'report':
            # Проверяем время последнего запроса отчета
            user_id = callback.from_user.id
            current_time = asyncio.get_event_loop().time()
            
            if user_id in self.last_report_request:
                time_since_last_request = current_time - self.last_report_request[user_id]
                if time_since_last_request < 3:  # Если прошло менее 3 секунд
                    await callback.answer("⏳ Отчет уже был запрошен! Подождите 3 секунды.", show_alert=True)
                    return
            
            try:
                # Обновляем время последнего запроса
                self.last_report_request[user_id] = current_time
                
                # Отправляем сообщение о начале генерации отчета
                status_message = await callback.message.edit_text("📊 Генерирую отчет по прибыльности...")
                
                # Генерируем отчет
                filename = self.excel_generator.generate_profitability_report()
                
                if filename and os.path.exists(filename):
                    # Отправляем файл
                    input_file = FSInputFile(filename)
                    await callback.message.answer_document(
                        document=input_file,
                        caption="📊 Отчет по прибыльности товаров готов!\n\n"
                                "В отчете содержится следующая информация:\n"
                                "• Название товара на Ozon\n"
                                "• Цена на Ozon\n"
                                "• Название товара на 1688\n"
                                "• Цена на 1688\n"
                                "• Прибыль\n"
                                "• Процент прибыли\n"
                                "• Вес и размеры\n"
                                "• Даты создания и обновления"
                    )
                    
                    # Удаляем файл после отправки
                    os.remove(filename)
                    
                    # Восстанавливаем главное меню
                    await callback.message.edit_text(
                        "👋 Привет! Я бот для анализа товаров Ozon и поиска аналогов на 1688.com\n\n"
                        "🎯 Что я умею:\n"
                        "• Парсинг товаров с Ozon\n"
                        "• Поиск аналогов на 1688.com\n"
                        "• Расчет прибыльности с учетом всех расходов\n"
                        "• Генерация отчетов в Excel\n"
                        "• Отслеживание статуса обработки\n\n"
                        "📝 Как использовать:\n"
                        "1. Отправьте мне ссылку на товар с Ozon\n"
                        "2. Я добавлю его в очередь на обработку\n"
                        "3. После обработки вы получите информацию о найденных аналогах\n\n"
                        "ℹ️ Поддерживаемые форматы ссылок:\n"
                        "• https://www.ozon.ru/product/...\n"
                        "• https://ozon.ru/t/...\n\n"
                        "🔍 Используйте кнопки ниже для навигации:",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await status_message.edit_text("❌ Не удалось сгенерировать отчет. Попробуйте позже.")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при генерации отчета: {str(e)}")
                await callback.message.edit_text("❌ Произошла ошибка при генерации отчета. Попробуйте позже.")
                
        elif action == 'help':
            # Проверяем время последнего запроса помощи
            user_id = callback.from_user.id
            current_time = asyncio.get_event_loop().time()
            
            if user_id in self.last_help_request:
                time_since_last_request = current_time - self.last_help_request[user_id]
                if time_since_last_request < 3:  # Если прошло менее 3 секунд
                    await callback.answer("⏳ Справка уже была запрошена! Подождите 3 секунды.", show_alert=True)
                    return
            
            try:
                # Обновляем время последнего запроса
                self.last_help_request[user_id] = current_time
                
                help_text = (
                    "🤖 Я бот для анализа товаров Ozon и поиска аналогов на 1688.com\n\n"
                    "📝 Как использовать:\n"
                    "1. Отправьте мне ссылку на товар с Ozon\n"
                    "2. Я добавлю его в очередь на обработку\n"
                    "3. После обработки вы получите информацию о найденных аналогах\n\n"
                    "📊 Функции:\n"
                    "• Парсинг товаров с Ozon\n"
                    "• Поиск аналогов на 1688.com\n"
                    "• Расчет прибыльности\n"
                    "• Получение отчетов в Excel\n\n"
                )
                
                # Проверяем, изменилось ли сообщение
                if callback.message.text != help_text:
                    try:
                        await callback.message.edit_text(help_text, reply_markup=get_main_keyboard())
                    except Exception as e:
                        if "message is not modified" in str(e):
                            # Если сообщение не изменилось, просто отвечаем на callback
                            await callback.answer("Справка актуальна")
                        else:
                            # Если другая ошибка, логируем её
                            logger.error(f"Ошибка при обновлении справки: {str(e)}")
                else:
                    # Если сообщение не изменилось, просто отвечаем на callback
                    await callback.answer("Справка актуальна")
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке запроса справки: {str(e)}")
                await callback.message.edit_text("❌ Произошла ошибка при обработке запроса. Попробуйте позже.")
        
        elif action == 'stats':
            try:
                # Получаем статистику
                stats = self.db.get_tasks_statistics()
                
                if not stats:
                    await callback.message.edit_text("❌ Не удалось получить статистику. Попробуйте позже.")
                    return
                
                # Формируем текст сообщения
                stats_text = "📊 Статистика по задачам:\n\n"
                
                # Общая информация
                stats_text += f"📦 Всего задач: {stats['total_tasks']}\n"
                stats_text += f"✅ Обработано товаров: {stats['completed_products']}\n"
                stats_text += f"💰 Средняя маржинальность: {stats['avg_profitability']}%\n\n"
                
                # Статусы задач
                stats_text += "📋 Статусы задач:\n"
                status_emojis = {
                    'pending': '⏳',
                    'ozon_processed': '🔄',
                    'completed': '✅',
                    'error': '❌',
                    'fatal': '💥',
                    'not_found': '🔍',
                    'failed': '⚠️'
                }
                
                for status, count in stats['status_counts'].items():
                    if count > 0:  # Показываем только ненулевые статусы
                        emoji = status_emojis.get(status, '•')
                        stats_text += f"{emoji} {status}: {count}\n"
                
                # Последние товары
                if stats['last_products']:
                    stats_text += "\n🆕 Последние обработанные товары:\n"
                    for product in stats['last_products']:
                        stats_text += f"• <a href='{product['ozon_url']}'>{product['name']}</a>\n"
                        stats_text += f"  <a href='{product['alibaba_url']}'>1688</a> | "
                        stats_text += f"Маржинальность: {product['profitability']}%\n"
                        stats_text += f"  Добавлен: {product['created_at']}\n\n"
                
                # Проверяем, изменилось ли сообщение
                if callback.message.text != stats_text:
                    try:
                        await callback.message.edit_text(stats_text, reply_markup=get_main_keyboard(), parse_mode='HTML')
                    except Exception as e:
                        if "message is not modified" in str(e):
                            # Если сообщение не изменилось, просто отвечаем на callback
                            await callback.answer("Статистика актуальна")
                        else:
                            # Если другая ошибка, логируем её
                            logger.error(f"Ошибка при обновлении статистики: {str(e)}")
                else:
                    # Если сообщение не изменилось, просто отвечаем на callback
                    await callback.answer("Статистика актуальна")
                
            except Exception as e:
                logger.error(f"❌ Ошибка при получении статистики: {str(e)}")
                await callback.message.edit_text("❌ Произошла ошибка при получении статистики. Попробуйте позже.")
        
        elif action == 'active':
            # Проверяем время последнего запроса активных задач
            user_id = callback.from_user.id
            current_time = asyncio.get_event_loop().time()
            
            if user_id in self.last_active_request:
                time_since_last_request = current_time - self.last_active_request[user_id]
                if time_since_last_request < 3:  # Если прошло менее 3 секунд
                    await callback.answer("⏳ Список активных задач уже был запрошен! Подождите 3 секунды.", show_alert=True)
                    return
            
            try:
                # Обновляем время последнего запроса
                self.last_active_request[user_id] = current_time
                
                # Получаем активные задачи (ограничиваем до 5 последних)
                active_tasks = self.db.get_active_tasks()[:5]
                
                if not active_tasks:
                    active_text = "📋 Активные задачи:\n\nВ данный момент нет задач в обработке."
                else:
                    # Формируем текст сообщения
                    active_text = "📋 Активные задачи (последние 5):\n\n"
                    
                    for task in active_tasks:
                        status_emoji = '⏳' if task['status'] == 'pending' else '🔄'
                        status_text = 'ожидает обработки' if task['status'] == 'pending' else 'обрабатывается на Ozon'
                        
                        # Ограничиваем длину названий товаров
                        ozon_name = task['ozon_name'][:50] + '...' if task['ozon_name'] and len(task['ozon_name']) > 50 else task['ozon_name']
                        alibaba_name = task['alibaba_name'][:50] + '...' if task['alibaba_name'] and len(task['alibaba_name']) > 50 else task['alibaba_name']
                        
                        active_text += f"{status_emoji} Задача #{task['task_id']}\n"
                        active_text += f"Статус: {status_text}\n"
                        active_text += f"Добавлена: {task['created_at']}\n"
                        
                        if task['ozon_name']:
                            active_text += f"Ozon: <a href='{task['ozon_url']}'>{ozon_name}</a>\n"
                        
                        if task['alibaba_name']:
                            active_text += f"1688: <a href='{task['alibaba_url']}'>{alibaba_name}</a>\n"
                        
                        active_text += "\n"
                    
                    # Если есть дополнительные задачи, добавляем уведомление
                    total_tasks = len(self.db.get_active_tasks())
                    if total_tasks > 5:
                        active_text += f"\n📝 Показаны последние 5 из {total_tasks} активных задач"
                
                # Проверяем длину сообщения
                if len(active_text) > 4000:  # Оставляем запас для кнопок и форматирования
                    active_text = active_text[:3997] + "..."
                
                # Проверяем, изменилось ли сообщение
                if callback.message.text != active_text:
                    try:
                        await callback.message.edit_text(active_text, reply_markup=get_main_keyboard(), parse_mode='HTML')
                    except Exception as e:
                        if "message is not modified" in str(e):
                            await callback.answer("Список активных задач актуален")
                        else:
                            logger.error(f"Ошибка при обновлении списка активных задач: {str(e)}")
                else:
                    await callback.answer("Список активных задач актуален")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при получении списка активных задач: {str(e)}")
                await callback.message.edit_text("❌ Произошла ошибка при получении списка активных задач. Попробуйте позже.")
        
        await callback.answer()
    
    async def handle_url(self, message: Message):
        """
        Обработчик URL-сообщений
        """
        url = message.text.strip()
        
        # Проверяем, что это ссылка на Ozon в одном из двух форматов
        if not (
            url.startswith('https://www.ozon.ru/product/') or 
            url.startswith('https://ozon.ru/t/')
        ):
            await message.answer(
                "❌ Пожалуйста, отправьте корректную ссылку на товар Ozon.\n"
                "Поддерживаются только следующие форматы:\n"
                "1. https://www.ozon.ru/product/...\n"
                "2. https://ozon.ru/t/..."
            )
            return
        
        # Проверяем, существует ли URL в базе
        if self.db.is_url_exists(url):
            # Получаем статус задачи
            task_status = self.db.get_task_status_by_url(url)
            
            # Получаем информацию о товаре
            product_info = self.db.get_product_info_by_url(url)
            
            # Формируем сообщение о статусе
            status_emoji = {
                'pending': '⏳',
                'ozon_processed': '🔄',
                'completed': '✅',
                'error': '❌',
                'fatal': '💥',
                'not_found': '🔍',
                'failed': '⚠️'
            }.get(task_status, '•')
            
            status_text = {
                'pending': 'ожидает обработки',
                'ozon_processed': 'обрабатывается на Ozon',
                'completed': 'обработан',
                'error': 'ошибка обработки',
                'fatal': 'критическая ошибка',
                'not_found': 'товар не найден',
                'failed': 'не удалось обработать'
            }.get(task_status, task_status)
            
            # Базовое сообщение о статусе
            status_message = f"📦 Товар уже находится в обработке!\nСтатус: {status_emoji} {status_text}\n\n"
            
            if product_info:
                # Добавляем информацию о товаре, если она есть
                status_message += f"🛍️ Ozon:\n"
                status_message += f"• Название: {product_info['ozon_name']}\n"
                status_message += f"• Цена: {product_info['ozon_price']} ₽ (${product_info['ozon_price_usd']})\n"
                status_message += f"• Ссылка: {product_info['ozon_url']}\n\n"
                
                status_message += f"🏭 1688:\n"
                status_message += f"• Название: {product_info['alibaba_name']}\n"
                status_message += f"• Цена: ${product_info['alibaba_price']}\n"
                status_message += f"• Ссылка: {product_info['alibaba_url']}\n\n"
                
                status_message += f"💰 Прибыльность:\n"
                status_message += f"• Маржинальность: {product_info['profitability_percent']}%\n"
                status_message += f"• Прибыль: ${product_info['total_profit']}\n\n"
                
                if product_info['weight']:
                    status_message += f"📏 Характеристики:\n"
                    status_message += f"• Вес: {product_info['weight']} г\n"
                    if product_info['dimensions']:
                        status_message += f"• Размеры: {product_info['dimensions']}\n"
                    status_message += "\n"
                
                status_message += f"📅 Добавлен: {product_info['created_at']}\n\n"
            
            status_message += "Хотите запустить повторную обработку этого товара?"
            
            # Получаем ID существующей задачи
            task_id = self.db.get_task_id_by_url(url)
            await message.answer(status_message, reply_markup=get_reprocess_keyboard(task_id))
            return
        
        try:
            # Добавляем задачу в базу
            task_id = self.db.add_task(url)
            await message.answer("✅ Задача установлена")
            logger.info(f"📥 Получена новая задача {task_id} от пользователя {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении задачи: {str(e)}")
            await message.answer("❌ Произошла ошибка при добавлении задачи. Попробуйте позже.")
    
    async def handle_callback(self, callback: CallbackQuery):
        """
        Обработчик callback-запросов от inline-кнопок
        """
        _, action, task_id = callback.data.split(':')
        task_id = int(task_id)
        
        if action == 'yes':
            try:
                # Получаем URL из существующей задачи
                url = self.db.get_task_url(task_id)
                if not url:
                    await callback.message.edit_text("❌ Ошибка: URL задачи не найден")
                    return
                
                # Добавляем новую задачу
                new_task_id = self.db.add_task(url)
                await callback.message.edit_text("✅ Задача установлена")
                logger.info(f"📥 Получена повторная задача {new_task_id} от пользователя {callback.from_user.id}")
            except Exception as e:
                logger.error(f"❌ Ошибка при добавлении повторной задачи: {str(e)}")
                await callback.message.edit_text("❌ Произошла ошибка при добавлении задачи. Попробуйте позже.")
        else:
            await callback.message.edit_text("❌ Отменено")
        
        await callback.answer()
    
    async def start(self):
        """
        Запуск бота
        """
        logger.info("🤖 Бот работает")
        await self.dp.start_polling(self.bot)