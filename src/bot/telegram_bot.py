import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import FSInputFile
from src.core.database import Database
from src.utils.logger import logger
from src.bot.keyboards import get_reprocess_keyboard, get_main_keyboard, get_subscription_keyboard, get_notifications_keyboard
from src.utils.excel_generator import ExcelGenerator
import os
from datetime import datetime, timedelta

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
        self.dp.message.register(self.handle_text, lambda msg: not msg.text.startswith('/'))
        self.dp.callback_query.register(self.handle_callback, lambda c: c.data.startswith('reprocess:') or c.data.startswith('action:') or c.data.startswith('subscription:') or c.data.startswith('admin_subscription:') or c.data.startswith('notifications:'))
    
    async def start_command(self, message: Message):
        """
        Обработчик команды /start
        """
        try:
            # Получаем пользователя
            user = self.db.get_user_by_telegram_id(message.from_user.id)
            
            # Если пользователь не существует, создаем нового
            if not user:
                user = self.db.add_user(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    first_name=message.from_user.first_name,
                    last_name=message.from_user.last_name
                )
            
            if not user:
                await message.answer("❌ Произошла ошибка при регистрации. Попробуйте позже.")
                return
            
            # Проверяем подписку
            subscription_info = self.db.check_subscription(user.id)
            if not subscription_info:
                await message.answer("❌ Ошибка при проверке подписки.")
                return
            
            # Формируем приветственное сообщение
            welcome_text = (
                f"👋 Привет, {message.from_user.first_name}!\n\n"
                f"🤖 Я бот для поиска товаров на 1688.com по товарам с Ozon.\n\n"
                f"💎 Информация о подписке:\n"
            )
            
            # Добавляем информацию о подписке
            if subscription_info['is_active']:
                if subscription_info['type'] == 'free':
                    welcome_text += (
                        f"• Тип: 🆓 Бесплатная\n"
                        f"• Доступно запросов: {subscription_info['requests_left']}/{subscription_info['requests_limit']}\n"
                    )
                elif subscription_info['type'] == 'limited':
                    end_date = subscription_info['end_date']
                    date_str = end_date.strftime('%d.%m.%Y') if end_date else 'Не указана'
                    welcome_text += (
                        f"• Тип: 💎 Расширенная\n"
                        f"• Доступно запросов: {subscription_info['requests_left']}/{subscription_info['requests_limit']}\n"
                        f"• Действует до: {date_str}\n"
                    )
                else:  # unlimited
                    end_date = subscription_info['end_date']
                    date_str = end_date.strftime('%d.%m.%Y') if end_date else 'Не указана'
                    welcome_text += (
                        f"• Тип: 👑 Безлимитная\n"
                        f"• Действует до: {date_str}\n"
                    )
            else:
                # Подписка неактивна
                if subscription_info['type'] == 'free':
                    welcome_text += (
                        f"• Тип: 🆓 Бесплатная\n"
                        f"• Использовано запросов: {subscription_info['requests_used']}/{subscription_info['requests_limit']}\n"
                        f"• Статус: ❌ Лимит запросов исчерпан\n"
                    )
                else:  # limited или unlimited
                    end_date = subscription_info['end_date']
                    date_str = end_date.strftime('%d.%m.%Y') if end_date else 'Не указана'
                    welcome_text += (
                        f"• Тип: {'💎 Расширенная' if subscription_info['type'] == 'limited' else '👑 Безлимитная'}\n"
                        f"• Статус: ❌ Подписка истекла {date_str}\n"
                    )
            
            welcome_text += (
                "\n📝 Просто отправьте мне ссылку на товар с Ozon, и я найду аналоги на 1688.com\n"
                "🔍 Поиск может занять некоторое время, пожалуйста, подождите."
            )
            
            # Отправляем приветственное сообщение с клавиатурой
            await message.answer(
                welcome_text,
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске бота: {e}")
            await message.answer("❌ Произошла ошибка при запуске бота. Попробуйте позже.")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()

    async def handle_action_callback(self, callback: CallbackQuery):
        """
        Обработчик callback-запросов для действий
        """
        try:
            # Получаем пользователя
            user = self.db.get_user_by_telegram_id(callback.from_user.id)
            if not user:
                await callback.answer("❌ Пожалуйста, начните с команды /start для регистрации.")
                return

            action = callback.data.split(':')[1]
            
            if action == 'close':
                # Удаляем сообщение
                await callback.message.delete()
                await callback.answer("✅ Сообщение закрыто")
                return
                
            elif action == 'notifications':
                # Получаем текущие настройки уведомлений
                enabled = self.db.get_notifications_settings(user.id)
                await callback.message.answer(
                    "🔔 *Настройки уведомлений*\n\n"
                    "Выберите действие:",
                    reply_markup=get_notifications_keyboard(enabled),
                    parse_mode="Markdown"
                )
                
            elif action == 'enable':
                # Включаем уведомления
                if self.db.update_notifications_settings(user.id, True):
                    await callback.message.edit_text(
                        "🔔 *Уведомления включены*\n\n"
                        "Вы будете получать уведомления о:\n"
                        "• Завершении обработки товаров\n"
                        "• Найденных аналогах\n"
                        "• Статусе обработки",
                        reply_markup=get_notifications_keyboard(True),
                        parse_mode="Markdown"
                    )
                else:
                    await callback.answer("❌ Ошибка при включении уведомлений.")
                    
            elif action == 'disable':
                # Выключаем уведомления
                if self.db.update_notifications_settings(user.id, False):
                    await callback.message.edit_text(
                        "🔕 *Уведомления выключены*\n\n"
                        "Вы не будете получать уведомления о:\n"
                        "• Завершении обработки товаров\n"
                        "• Найденных аналогах\n"
                        "• Статусе обработки",
                        reply_markup=get_notifications_keyboard(False),
                        parse_mode="Markdown"
                    )
                else:
                    await callback.answer("❌ Ошибка при выключении уведомлений.")

            elif action == 'subscription':
                # Проверяем статус подписки
                subscription_info = self.db.check_subscription(user.id)
                if not subscription_info:
                    await callback.answer("❌ Ошибка при получении информации о подписке.")
                    return
            
                # Получаем информацию о типах подписок
                subscription_types = self.db.get_subscription_info()
                
                # Формируем сообщение
                message = "💎 Информация о подписках:\n\n"
                
                # Добавляем информацию о текущей подписке
                if subscription_info['is_active']:
                    if subscription_info['type'] == 'free':
                        message += f"🆓 Ваша текущая подписка: Бесплатная\n"
                        message += f"Осталось запросов: {subscription_info['requests_left']}/{subscription_info['requests_limit']}\n\n"
                    elif subscription_info['type'] == 'limited':
                        end_date = subscription_info['end_date']
                        date_str = end_date.strftime('%d.%m.%Y') if end_date else 'Не указана'
                        message += f"💎 Ваша текущая подписка: Расширенная\n"
                        message += f"Осталось запросов: {subscription_info['requests_left']}/{subscription_info['requests_limit']}\n"
                        message += f"Действует до: {date_str}\n\n"
                    else:  # unlimited
                        end_date = subscription_info['end_date']
                        date_str = end_date.strftime('%d.%m.%Y') if end_date else 'Не указана'
                        message += f"👑 Ваша текущая подписка: Безлимитная\n"
                        message += f"Действует до: {date_str}\n\n"
                else:
                    if subscription_info['type'] == 'free':
                        message += "❌ У вас нет активной подписки\n"
                        message += "🆓 Тип последней подписки: Бесплатная\n"
                        message += f"Использовано запросов: {subscription_info['requests_used']}/{subscription_info['requests_limit']}\n"
                        message += "❗ Лимит запросов исчерпан\n\n"
                    elif subscription_info['type'] in ['limited', 'unlimited']:
                        message += "❌ У вас нет активной подписки\n"
                        message += f"💎 Тип последней подписки: {'Расширенная' if subscription_info['type'] == 'limited' else 'Безлимитная'}\n"
                        message += "❗ Срок действия истек\n\n"
                
                # Добавляем информацию о доступных подписках
                message += "📋 Доступные подписки:\n\n"
                
                for sub_type, info in subscription_types.items():
                    if sub_type != 'free':  # Показываем только платные подписки
                        message += f"{info['name']} - {info['price']} ₽\n"
                        message += f"Количество запросов: {info['requests']}\n"
                        message += "Включает:\n"
                        for feature in info['features']:
                            message += f"• {feature}\n"
                        message += "\n"
                
                message += "📞 Для оформления подписки свяжитесь с менеджером."
                
                await callback.message.answer(
                    message,
                    reply_markup=get_subscription_keyboard(subscription_info, user.is_admin)
                )
            
            elif action == 'stats':
                # Проверяем ограничение на запросы статистики
                current_time = datetime.now()
                if callback.from_user.id in self.last_stats_request:
                    time_diff = (current_time - self.last_stats_request[callback.from_user.id]).total_seconds()
                    if time_diff < 5:  # 5 секунд между запросами
                        await callback.answer("⚠️ Пожалуйста, подождите 5 секунд перед следующим запросом статистики.")
                        return
                
                self.last_stats_request[callback.from_user.id] = current_time
                
                # Получаем статистику для пользователя
                stats = self.db.get_tasks_statistics(user.id)
                
                if not stats:
                    await callback.answer("❌ Нет данных для отображения статистики.")
                    return
                
                stats_text = (
                    f"📊 *Статистика ваших задач:*\n\n"
                    f"📈 Всего задач: {stats['total']}\n"
                    f"✅ Выполнено: {stats['completed']}\n"
                    f"❌ Не найдено: {stats['not_found']}\n"
                    f"⚠️ Ошибки: {stats['error']}\n"
                    f"🚫 Критические ошибки: {stats['failed']}\n"
                    f"💀 Фатальные ошибки: {stats['fatal']}\n"
                    f"⏳ В обработке: {stats['ozon_processed']}\n"
                    f"📝 В очереди: {stats['pending']}"
                )
                # Создаем клавиатуру с кнопкой "Закрыть"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")]
                ])
                await callback.message.answer(stats_text, parse_mode="Markdown", reply_markup=keyboard)
                
            elif action == 'report':
                # Проверяем ограничение на запросы отчетов
                current_time = datetime.now()
                if callback.from_user.id in self.last_report_request:
                    time_diff = (current_time - self.last_report_request[callback.from_user.id]).total_seconds()
                    if time_diff < 5:  # 5 секунд между запросами
                        await callback.answer("⚠️ Пожалуйста, подождите 5 секунд перед следующим запросом отчета.")
                        return
                
                self.last_report_request[callback.from_user.id] = current_time
                
                # Получаем задачи пользователя
                tasks = self.db.get_user_tasks(user.id)
                if not tasks:
                    await callback.answer("❌ Нет данных для генерации отчета.")
                    return
                
                # Генерируем отчет
                report_path = self.excel_generator.generate_report(tasks)
                if report_path:
                    report_file = FSInputFile(report_path)
                    await callback.message.answer_document(
                        document=report_file,
                        caption="📊 *Ваш отчет готов!*",
                        parse_mode="Markdown"
                    )
                    # Удаляем временный файл
                    os.remove(report_path)
                else:
                    await callback.answer("❌ Ошибка при генерации отчета. Пожалуйста, попробуйте позже.")
                
            elif action == 'active':
                # Проверяем ограничение на запросы активных задач
                current_time = datetime.now()
                if callback.from_user.id in self.last_active_request:
                    time_diff = (current_time - self.last_active_request[callback.from_user.id]).total_seconds()
                    if time_diff < 5:  # 5 секунд между запросами
                        await callback.answer("⚠️ Пожалуйста, подождите 5 секунд перед следующим запросом активных задач.")
                        return
                
                self.last_active_request[callback.from_user.id] = current_time
                
                # Получаем активные задачи пользователя
                tasks = self.db.get_user_tasks(user.id, status='active')
                if not tasks:
                    await callback.answer("❌ У вас нет активных задач.")
                    return
            
                active_text = "📝 *Ваши активные задачи:*\n\n"
                for task in tasks:
                    status_emoji = "⏳" if task['status'] == 'pending' else "🔍"
                    status_text = "Ожидает обработки" if task['status'] == 'pending' else "Обрабатывается..."
                    active_text += f"{status_emoji} *{status_text}*\n"
                    active_text += f"🔗 {task['url']}\n"
                    active_text += f"📅 Добавлена: {task['created_at'].strftime('%d.%m.%Y %H:%M')}\n\n"
                
                # Создаем клавиатуру с кнопкой "Закрыть"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")]
                ])
                
                await callback.message.answer(active_text, parse_mode="Markdown", reply_markup=keyboard)
                
            elif action == 'help':
                # Проверяем ограничение на запросы помощи
                current_time = datetime.now()
                if callback.from_user.id in self.last_help_request:
                    time_diff = (current_time - self.last_help_request[callback.from_user.id]).total_seconds()
                    if time_diff < 5:  # 5 секунд между запросами
                        await callback.answer("⚠️ Пожалуйста, подождите 5 секунд перед следующим запросом помощи.")
                        return
                
                self.last_help_request[callback.from_user.id] = current_time
                
                help_text = (
                    "🤖 *Как использовать бота:*\n\n"
                    "1️⃣ Отправьте ссылку на товар с Ozon\n"
                    "2️⃣ Бот добавит товар в очередь на обработку\n"
                    "3️⃣ После обработки вы получите информацию о найденных аналогах\n\n"
                    "💎 *Система подписок:*\n"
                    "• 🆓 Бесплатная подписка: 3 запроса\n"
                    "• 💎 Расширенная подписка: 100 запросов в месяц\n"
                    "• 👑 Безлимитная подписка: неограниченное количество запросов\n\n"
                    "📊 *Статистика:*\n"
                    "• Показывает количество задач по статусам\n"
                    "• Обновляется каждую минуту\n"
                    "• Доступна для всех типов подписок\n\n"
                    "📈 *Отчеты:*\n"
                    "• Генерируются в формате Excel\n"
                    "• Содержат подробную информацию о товарах\n"
                    "• Включают данные о прибыльности\n\n"
                    "📝 *Активные задачи:*\n"
                    "• Показывает задачи в очереди\n"
                    "• Обновляется каждую минуту\n"
                    "• Отображает статус обработки\n\n"
                    "💡 *Дополнительные возможности:*\n"
                    "• Повторная обработка товаров\n"
                    "• Поддержка менеджера\n\n"
                    "📞 *Поддержка:*\n"
                    "• По всем вопросам обращайтесь к менеджеру\n"
                    "• Помощь в оформлении подписки\n"
                    "• Техническая поддержка"
                )

                # Создаем клавиатуру с кнопкой "Закрыть"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")]
                ])
                await callback.message.answer(help_text, reply_markup=keyboard, parse_mode="Markdown")
                
            elif action == 'show_all_users':
                # Проверяем, является ли пользователь админом
                if not user.is_admin:
                    await callback.answer("❌ У вас нет прав администратора.")
                    return
                
                # Получаем список всех пользователей
                users = self.db.get_all_users()
                if not users or len(users) == 0:
                    await callback.answer("❌ Пользователи не найдены.")
                    return
                
                # Отправляем общую информацию о пользователях
                await callback.message.answer(
                    f"👥 *Список пользователей* (всего: {len(users)})\n\n"
                    f"Ниже будет показан список всех пользователей с возможностью управления их подписками.",
                    parse_mode="Markdown"
                )
                
                # Отправляем информацию о каждом пользователе отдельным сообщением
                for i, user_data in enumerate(users[:10], 1):  # Ограничиваем до 10 пользователей
                    # Получаем информацию о подписке пользователя
                    subscription = self.db.check_subscription(user_data['id'])
                    
                    # Формируем строку с информацией о пользователе
                    user_info = f"{i}. {user_data['first_name'] or ''} {user_data['last_name'] or ''} (@{user_data['username'] or 'без имени'})\n"
                    user_info += f"   ID: {user_data['id']}\n"
                    
                    if subscription:
                        sub_status = "✅ Активна" if subscription['is_active'] else "❌ Неактивна"
                        sub_type = ""
                        if subscription['type'] == 'free':
                            sub_type = "🆓 Бесплатная"
                        elif subscription['type'] == 'limited':
                            sub_type = "💎 Расширенная"
                        elif subscription['type'] == 'unlimited':
                            sub_type = "👑 Безлимитная"
                        elif subscription['type'] == 'admin':
                            sub_type = "👑 Администратор"
                        
                        user_info += f"   Подписка: {sub_type} ({sub_status})\n"
                        
                        if subscription['type'] not in ['unlimited', 'admin']:
                            user_info += f"   Запросы: {subscription['requests_used']}/{subscription['requests_limit']}\n"
                        
                        if subscription['end_date']:
                            date_str = subscription['end_date'].strftime('%d.%m.%Y') if subscription['end_date'] else 'Не указана'
                            user_info += f"   Действует до: {date_str}\n"
                    else:
                        user_info += "   Подписка: нет данных\n"
                    
                    # Добавляем кнопки для управления подпиской пользователя
                    keyboard = [
                        [
                            InlineKeyboardButton(text="💎 Расширенная", callback_data=f"admin_subscription:activate:limited:{user_data['id']}"),
                            InlineKeyboardButton(text="👑 Безлимитная", callback_data=f"admin_subscription:activate:unlimited:{user_data['id']}")
                        ],
                        [
                            InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
                        ]
                    ]
                    
                    # Отправляем сообщение с информацией о пользователе и кнопками
                    await callback.message.answer(
                        user_info,
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                        parse_mode="Markdown"
                    )
                
                # Если пользователей больше 10, добавляем сообщение о том, что показаны не все
                if len(users) > 10:
                    await callback.message.answer(
                        f"ℹ️ Показано 10 из {len(users)} пользователей.\n"
                        f"Для поиска конкретного пользователя используйте кнопку 'Найти пользователя'.",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="🔙 Назад", callback_data="subscription:admin")]
                        ]),
                        parse_mode="Markdown"
                    )
                
                return
                
            elif action == 'system_stats':
                # Проверяем, является ли пользователь админом
                if not user.is_admin:
                    await callback.answer("❌ У вас нет прав администратора.")
                    return
                
                # Получаем список всех пользователей
                users = self.db.get_all_users()
                
                # Считаем статистику
                total_users = len(users)
                admin_users = sum(1 for user in users if user['is_admin'])
                
                # Счетчики подписок
                free_subs = 0
                limited_subs = 0
                unlimited_subs = 0
                active_subs = 0
                
                # Подсчитываем статистику подписок
                for user_data in users:
                    subscription = self.db.check_subscription(user_data['id'])
                    if subscription['is_active']:
                        active_subs += 1
                    
                    if subscription['type'] == 'free':
                        free_subs += 1
                    elif subscription['type'] == 'limited':
                        limited_subs += 1
                    elif subscription['type'] == 'unlimited' or subscription['type'] == 'admin':
                        unlimited_subs += 1
                
                # Получаем общую статистику задач
                task_stats = self.db.get_tasks_statistics()
                
                # Формируем сообщение
                stats_message = (
                    "📊 *Системная статистика*\n\n"
                    f"👥 *Пользователи:*\n"
                    f"• Всего пользователей: {total_users}\n"
                    f"• Администраторов: {admin_users}\n"
                    f"• Активных подписок: {active_subs}\n\n"
                    f"💎 *Подписки:*\n"
                    f"• 🆓 Бесплатные: {free_subs}\n"
                    f"• 💎 Расширенные: {limited_subs}\n"
                    f"• 👑 Безлимитные: {unlimited_subs}\n\n"
                    f"🔄 *Задачи:*\n"
                )
                
                if task_stats:
                    stats_message += (
                        f"• Всего задач: {task_stats.get('total', 0)}\n"
                        f"• Выполнено: {task_stats.get('completed', 0)}\n"
                        f"• Не найдено: {task_stats.get('not_found', 0)}\n"
                        f"• С ошибками: {task_stats.get('error', 0) + task_stats.get('failed', 0) + task_stats.get('fatal', 0)}\n"
                        f"• В обработке: {task_stats.get('ozon_processed', 0) + task_stats.get('pending', 0)}\n"
                    )
                else:
                    stats_message += "• Нет данных о задачах\n"
                
                # Создаем клавиатуру для закрытия
                keyboard = [
                    [
                        InlineKeyboardButton(text="🔙 Назад", callback_data="subscription:admin"),
                        InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
                    ]
                ]
                
                await callback.message.answer(
                    stats_message,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                    parse_mode="Markdown"
                )
                
                return
                
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Ошибка при обработке callback: {e}")
            await callback.answer("❌ Произошла ошибка при обработке запроса.")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()

    async def handle_subscription_callback(self, callback: CallbackQuery):
        """
        Обработчик callback-запросов для подписок
        """
        try:
            # Получаем пользователя
            user = self.db.get_user_by_telegram_id(callback.from_user.id)
            if not user:
                await callback.answer("❌ Пожалуйста, начните с команды /start для регистрации.")
                return

            action = callback.data.split(':')[1]
            
            if action == 'admin':
                # Проверяем, является ли пользователь админом
                if not user.is_admin:
                    await callback.answer("❌ У вас нет прав администратора.")
                    return
                
                # Создаем панель администратора
                admin_menu = (
                    "👤 *Административная панель*\n\n"
                    "Добро пожаловать в панель администратора бота.\n"
                    "Вы можете управлять пользователями и просматривать статистику системы."
                )
                
                # Создаем клавиатуру для администратора
                admin_keyboard = [
                    [
                        InlineKeyboardButton(text="👥 Показать всех пользователей", callback_data="action:show_all_users")
                    ],
                    [
                        InlineKeyboardButton(text="📊 Статистика системы", callback_data="action:system_stats")
                    ],
                    [
                        InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
                    ]
                ]
                
                # Отправляем сообщение с меню администратора
                await callback.message.answer(
                    admin_menu,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=admin_keyboard),
                    parse_mode="Markdown"
                )
                
                return
                
            elif action == 'info':
                # Проверяем статус подписки
                subscription_info = self.db.check_subscription(user.id)
                if not subscription_info:
                    await callback.answer("❌ Ошибка при получении информации о подписке.")
                    return
                
                # Формируем сообщение с информацией о подписке
                message = "💎 *Информация о вашей подписке:*\n\n"
                
                if subscription_info['is_active']:
                    if subscription_info['type'] == 'free':
                        message += (
                            "🆓 *Тип подписки:* Бесплатная\n"
                            f"📊 *Использовано запросов:* {subscription_info['requests_used']}/{subscription_info['requests_limit']}\n"
                            f"📊 *Осталось запросов:* {subscription_info['requests_left']}\n"
                            "📅 *Срок действия:* Бессрочно\n\n"
                        )
                    elif subscription_info['type'] == 'limited':
                        message += (
                            "💎 *Тип подписки:* Расширенная\n"
                            f"📊 *Использовано запросов:* {subscription_info['requests_used']}/{subscription_info['requests_limit']}\n"
                            f"📊 *Осталось запросов:* {subscription_info['requests_left']}\n"
                            f"📅 *Действует до:* {subscription_info['end_date'].strftime('%d.%m.%Y') if subscription_info['end_date'] else 'Не указана'}\n\n"
                        )
                    else:  # unlimited
                        message += (
                            "👑 *Тип подписки:* Безлимитная\n"
                            "📊 *Запросы:* Без ограничений\n"
                            f"📅 *Действует до:* {subscription_info['end_date'].strftime('%d.%m.%Y') if subscription_info['end_date'] else 'Не указана'}\n\n"
                        )
                else:
                    if subscription_info['type'] == 'free':
                        message += (
                            "❌ *Подписка неактивна*\n"
                            "🆓 *Тип подписки:* Бесплатная\n"
                            f"📊 *Использовано запросов:* {subscription_info['requests_used']}/{subscription_info['requests_limit']}\n"
                            "❗ *Лимит запросов исчерпан*\n\n"
                        )
                    elif subscription_info['type'] in ['limited', 'unlimited']:
                        message += (
                            "❌ *Подписка неактивна*\n"
                            f"💎 *Тип подписки:* {'Расширенная' if subscription_info['type'] == 'limited' else 'Безлимитная'}\n"
                            "❗ *Срок действия истек*\n\n"
                        )
                
                # Добавляем информацию о доступных подписках
                message += "📋 *Доступные подписки:*\n\n"
                subscription_types = self.db.get_subscription_info()
                
                for sub_type, info in subscription_types.items():
                    if sub_type != 'free':  # Показываем только платные подписки
                        message += f"*{info['name']}* - {info['price']} ₽\n"
                        message += f"📊 Количество запросов: {info['requests']}\n"
                        message += "✨ Включает:\n"
                        for feature in info['features']:
                            message += f"• {feature}\n"
                        message += "\n"
                
                message += "📞 *Для оформления подписки свяжитесь с менеджером.*"
                
                await callback.message.answer(
                    message,
                    reply_markup=get_subscription_keyboard(subscription_info, user.is_admin),
                    parse_mode="Markdown"
                )
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке callback подписки: {e}")
            await callback.answer("❌ Произошла ошибка при обработке запроса.")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()

    async def handle_admin_subscription_callback(self, callback: CallbackQuery):
        """
        Обработчик callback-запросов для администраторского управления подписками
        """
        # Получаем данные из callback
        data = callback.data.replace('admin_subscription:', '')
        parts = data.split(':')
        
        if len(parts) < 3:
            await callback.answer("❌ Неверный формат данных")
            return
        
        action = parts[0]  # Действие (activate)
        sub_type = parts[1]  # Тип подписки (limited, unlimited)
        user_id = int(parts[2])  # ID пользователя для выдачи подписки
        
        # Получаем пользователя, который вызвал callback
        admin_user = self.db.get_user_by_telegram_id(callback.from_user.id)
        if not admin_user or not admin_user.is_admin:
            await callback.answer("❌ У вас нет прав администратора")
            return
            
        # Получаем пользователя, которому выдаем подписку
        target_user = self.db.get_user_by_id(user_id)
        if not target_user:
            await callback.answer(f"❌ Пользователь с ID {user_id} не найден")
            return
            
        if action == 'activate':
            # Определяем параметры подписки
            days = 30  # Стандартная подписка на 30 дней
            requests_limit = None
            
            if sub_type == 'limited':
                requests_limit = 100  # 100 запросов для расширенной подписки
                subscription_name = "💎 Расширенная"
            elif sub_type == 'unlimited':
                requests_limit = None  # Без ограничений для безлимитной
                subscription_name = "👑 Безлимитная"
            else:
                await callback.answer("❌ Неизвестный тип подписки")
                return
                
            # Активируем подписку
            success = self.db.activate_subscription(
                user_id=target_user.id,
                subscription_type=sub_type,
                days=days,
                requests_limit=requests_limit
            )
            
            if success:
                # Отправляем сообщение администратору
                await callback.answer(f"✅ Подписка успешно выдана пользователю")
                
                # Формируем сообщение о выдаче подписки
                end_date = (datetime.now() + timedelta(days=days)).strftime('%d.%m.%Y')
                admin_msg = (
                    f"✅ *Подписка успешно выдана*\n\n"
                    f"👤 Пользователь: {target_user.first_name or ''} {target_user.last_name or ''} (@{target_user.username or 'без имени'})\n"
                    f"🆔 ID: {target_user.id}\n"
                    f"📝 Тип: {subscription_name}\n"
                    f"📆 Период: {days} дней (до {end_date})\n"
                )
                
                if requests_limit:
                    admin_msg += f"🔢 Запросы: {requests_limit}\n"
                else:
                    admin_msg += f"🔢 Запросы: Без ограничений\n"
                
                await callback.message.answer(
                    admin_msg,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Назад", callback_data="subscription:admin")]
                    ])
                )
                
                # Отправляем уведомление пользователю о новой подписке
                try:
                    user_msg = (
                        f"🎉 *Поздравляем! Вам выдана новая подписка!*\n\n"
                        f"📝 Тип: {subscription_name}\n"
                        f"📆 Период: {days} дней (до {end_date})\n"
                    )
                    
                    if requests_limit:
                        user_msg += f"🔢 Запросы: {requests_limit}\n"
                    else:
                        user_msg += f"🔢 Запросы: Без ограничений\n"
                    
                    # Добавляем информацию об отправителе
                    user_msg += f"\n👤 Подписка выдана администратором"
                    
                    await self.bot.send_message(
                        chat_id=target_user.telegram_id,
                        text=user_msg,
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления пользователю: {e}")
                    await callback.message.answer("⚠️ Подписка выдана, но не удалось отправить уведомление пользователю")
            else:
                await callback.answer("❌ Не удалось активировать подписку")
                
        else:
            await callback.answer("❌ Неизвестное действие")

    async def handle_url(self, message: Message):
        """
        Обработчик URL-сообщений
        """
        try:
            # Получаем пользователя
            user = self.db.get_user_by_telegram_id(message.from_user.id)
            if not user:
                await message.answer("❌ Пожалуйста, начните с команды /start для регистрации.")
                return

            # Проверяем статус подписки
            subscription_info = self.db.check_subscription(user.id)
            if not subscription_info:
                await message.answer("❌ Ошибка при проверке подписки.")
                return

            # Проверяем активность подписки и лимиты запросов
            if not subscription_info['is_active']:
                await message.answer(
                    "❌ *Ваша подписка неактивна.*\n\n"
                    "💎 *Доступные подписки:*\n"
                    "• 💎 Расширенная: 100 запросов в месяц\n"
                    "• 👑 Безлимитная: неограниченное количество\n\n"
                    "📞 Для оформления подписки свяжитесь с менеджером.",
                    reply_markup=get_subscription_keyboard(subscription_info, user.is_admin),
                    parse_mode="Markdown"
                )
                return

            # Проверяем лимит запросов для всех типов подписок кроме unlimited и админов
            if not user.is_admin and subscription_info['type'] != 'unlimited':
                current_requests = self.db.get_user_by_telegram_id(message.from_user.id).requests_used
                requests_limit = subscription_info['requests_limit']
                
                if current_requests >= requests_limit:
                    await message.answer(
                        f"❌ *У вас закончились доступные запросы.*\n\n"
                        f"Тип подписки: {subscription_info['type']}\n"
                        f"Использовано запросов: {current_requests}/{requests_limit}\n\n"
                        "💎 *Доступные подписки:*\n"
                        "• 💎 Расширенная: 100 запросов в месяц\n"
                        "• 👑 Безлимитная: неограниченное количество\n\n"
                        "📞 Для оформления подписки свяжитесь с менеджером.",
                        reply_markup=get_subscription_keyboard(subscription_info, user.is_admin),
                        parse_mode="Markdown"
                    )
                    return

            # Проверяем, является ли сообщение URL
            if not message.text.startswith(('http://', 'https://')):
                await message.answer("❌ Пожалуйста, отправьте корректную ссылку на товар.")
                return

            # Проверяем, является ли URL ссылкой на Ozon
            if 'ozon.ru' not in message.text:
                await message.answer("❌ Пожалуйста, отправьте ссылку на товар с Ozon.")
                return

            # Увеличиваем счетчик использованных запросов ДО добавления задачи
            if not user.is_admin and subscription_info['type'] != 'unlimited':
                if not self.db.increment_requests_used(user.id):
                    await message.answer("❌ Ошибка при обработке запроса. Попробуйте позже.")
                    return

            # Добавляем задачу в базу данных
            task_id = self.db.add_task(message.text, user.id)
            if not task_id:
                # Если не удалось добавить задачу, возвращаем использованный запрос
                if not user.is_admin and subscription_info['type'] != 'unlimited':
                    self.db.decrement_requests_used(user.id)
                await message.answer("❌ Ошибка при добавлении задачи. Попробуйте позже.")
                return

            # Отправляем сообщение о успешном добавлении задачи
            await message.answer(
                "✅ *Задача добавлена в очередь на обработку.*\n\n"
                "⏳ *Статус:*\n"
                "• Задача принята\n"
                "• Ожидает обработки\n"
                "• Результаты будут отправлены автоматически\n\n"
                "💡 Используйте кнопку *Активные задачи* для просмотра статуса.",
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )

            logger.info(f"📥 Получена новая задача {task_id} от пользователя {message.from_user.id}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке URL: {str(e)}")
            await message.answer("❌ Произошла ошибка при обработке запроса. Попробуйте позже.")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()
    
    async def handle_reprocess_callback(self, callback: CallbackQuery) -> None:
        """
        Обработчик callback запросов для перезапуска задач
        """
        try:
            # Получаем данные из callback
            data = callback.data.replace('reprocess:', '')
            task_id = int(data)
            
            # Получаем пользователя, который вызвал callback
            user = self.db.get_user_by_telegram_id(callback.from_user.id)
            if not user:
                await callback.answer("❌ Пользователь не найден")
                return
                
            # Получаем задачу
            task = self.db.get_task(task_id)
            if not task:
                await callback.answer("❌ Задача не найдена")
                return
                
            # Проверяем, принадлежит ли задача пользователю
            if task.user_id != user.id and not user.is_admin:
                await callback.answer("❌ У вас нет прав для перезапуска этой задачи")
                return
                
            # Проверяем подписку пользователя
            subscription = self.db.check_subscription(user.id)
            if not subscription['is_active']:
                # Подписка неактивна, уведомляем пользователя и предлагаем обновить подписку
                subscription_type = subscription['type']
                
                # Формируем сообщение в зависимости от типа подписки
                if subscription_type == 'free':
                    message = (
                        "❌ *Невозможно перезапустить задачу*\n\n"
                        "Ваша бесплатная подписка израсходована.\n"
                        f"Использовано запросов: {subscription['requests_used']}/{subscription['requests_limit']}\n\n"
                        "Приобретите платную подписку для продолжения работы."
                    )
                else:
                    message = (
                        "❌ *Невозможно перезапустить задачу*\n\n"
                        "Ваша подписка истекла.\n\n"
                        "Обновите подписку для продолжения работы."
                    )
                
                # Создаем клавиатуру с кнопкой обновления подписки
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💎 Обновить подписку", callback_data="subscription:info")]
                ])
                
                await callback.message.answer(message, reply_markup=keyboard, parse_mode="Markdown")
                return
                
            # Перезапускаем задачу, меняя ее статус на 'pending'
            success = self.db.update_task_status(task_id, 'pending')
            
            if success:
                # Уведомляем пользователя об успешном перезапуске
                await callback.answer("✅ Задача успешно добавлена в очередь на повторную обработку")
                
                # Увеличиваем счетчик использованных запросов
                self.db.increment_requests_used(user.id)
                
                # Отправляем подробное сообщение о перезапуске
                await callback.message.answer(
                    f"🔄 *Задача перезапущена*\n\n"
                    f"URL: {task.url}\n"
                    f"ID задачи: {task_id}\n\n"
                    f"Задача добавлена в очередь и будет обработана в ближайшее время. "
                    f"Вы получите уведомление, когда обработка будет завершена.",
                    parse_mode="Markdown"
                )
            else:
                await callback.answer("❌ Ошибка при перезапуске задачи")
        
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса на перезапуск задачи: {e}")
            await callback.answer("❌ Произошла ошибка при обработке запроса")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()
    
    async def handle_callback(self, callback: CallbackQuery):
        """
        Обработчик всех callback запросов от inline кнопок
        """
        try:
            # Получаем данные из callback
            data = callback.data
            
            if data.startswith('subscription:'):
                await self.handle_subscription_callback(callback)
            elif data.startswith('action:'):
                await self.handle_action_callback(callback)
            elif data.startswith('admin_subscription:'):
                await self.handle_admin_subscription_callback(callback)
            elif data.startswith('reprocess:'):
                await self.handle_reprocess_callback(callback)
            else:
                # Неизвестный тип callback
                await callback.answer("❌ Неизвестная команда")
                
        except Exception as e:
            logger.error(f"Ошибка при обработке callback: {e}")
            await callback.answer("❌ Произошла ошибка при обработке команды")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()
            
    async def start(self):
        """
        Запуск бота
        """
        logger.info("🤖 Бот работает")
        await self.dp.start_polling(self.bot)

    async def send_task_results(self, task_id: int):
        """
        Отправляет результаты обработки задачи пользователю
        """
        try:
            # Получаем информацию о задаче
            task = self.db.get_task(task_id)
            if not task:
                return

            # Получаем пользователя
            user = self.db.get_user_by_id(task.user_id)
            if not user:
                return

            # Проверяем настройки уведомлений
            if not self.db.get_notifications_settings(user.id):
                return

            # Формируем сообщение с результатами
            message = (
                f"✅ *Задача завершена!*\n\n"
                f"🔗 *Товар:* {task.url}\n"
                f"📊 *Статус:* {task.status}\n"
                f"⏱ *Время обработки:* {task.processing_time:.2f} сек\n\n"
            )

            # Добавляем информацию о найденных аналогах
            if task.status == 'completed':
                analogs = self.db.get_task_analogs(task_id)
                if analogs:
                    message += "📦 *Найденные аналоги:*\n\n"
                    for analog in analogs:
                        message += (
                            f"• *Название:* {analog['title']}\n"
                            f"  *Цена:* {analog['price']} $\n"
                            f"  *Прибыль:* {analog['profit']} $\n"
                            f"  *Маржинальность:* {analog['margin']:.1f}%\n"
                            f"  *Ссылка:* {analog['url']}\n\n"
                        )
                else:
                    message += "❌ Аналоги не найдены\n\n"

            # Добавляем информацию об ошибках
            if task.status in ['error', 'failed', 'fatal']:
                message += f"⚠️ *Ошибка:* {task.error_message}\n\n"

            # Добавляем кнопку для повторной обработки
            message += "🔄 Используйте кнопку *Повторить* для повторной обработки."

            # Отправляем сообщение пользователю
            await self.bot.send_message(
                chat_id=user.telegram_id,
                text=message,
                reply_markup=get_reprocess_keyboard(task_id),
                parse_mode="Markdown"
            )

            logger.info(f"📤 Отправлены результаты задачи {task_id} пользователю {user.telegram_id}")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке результатов задачи {task_id}: {e}")
        finally:
            # Закрываем сессию базы данных
            self.db.close_session()

    async def handle_text(self, message: Message):
        """
        Обработчик текстовых сообщений
        """
        try:
            # Проверяем, является ли сообщение URL
            if message.text.startswith(('http://', 'https://')):
                # Перенаправляем обработку URL в специализированный метод
                await self.handle_url(message)
                return
            
            # Если это не URL, отправляем сообщение с инструкцией
            await message.answer(
                "❌ Пожалуйста, отправьте ссылку на товар с Ozon.\n\n"
                "💡 Ссылка должна начинаться с http:// или https:// и содержать ozon.ru",
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке текстового сообщения: {e}")
            await message.answer("❌ Произошла ошибка при обработке сообщения. Попробуйте позже.")
        finally:
            self.db.close_session()