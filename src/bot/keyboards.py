#!/usr/bin/env python
# -*- coding: utf-8 -*-

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_reprocess_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для повторной обработки задачи
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔄 Повторить",
                callback_data=f"reprocess:{task_id}"
            )
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_main_keyboard() -> InlineKeyboardMarkup:
    """
    Создает основную клавиатуру бота
    """
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="action:stats"),
            InlineKeyboardButton(text="📈 Отчет", callback_data="action:report")
        ],
        [
            InlineKeyboardButton(text="📝 Активные задачи", callback_data="action:active"),
            InlineKeyboardButton(text="💎 Подписка", callback_data="action:subscription")
        ],
        [
            InlineKeyboardButton(text="❓ Помощь", callback_data="action:help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_subscription_keyboard(subscription_info: dict, is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для управления подпиской
    """
    keyboard = []
    
    if is_admin:
        keyboard.append([
            InlineKeyboardButton(text="👑 Админ панель", callback_data="subscription:admin")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton(text="ℹ️ Информация", callback_data="subscription:info")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="📞 Связаться с менеджером", url="https://t.me/mesto665")
    ])
    
    keyboard.append([
        InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_notifications_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для управления уведомлениями
    """
    keyboard = [
        [
            InlineKeyboardButton(
                text="🔔 Включить" if not enabled else "🔕 Выключить",
                callback_data=f"action:enable" if not enabled else "action:disable"
            )
        ],
        [
            InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_subscription_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для управления подписками (только для админов)
    """
    keyboard = [
        [
            InlineKeyboardButton(text="💎 Расширенная", callback_data=f"admin_subscription:activate:limited:{user_id}"),
            InlineKeyboardButton(text="👑 Безлимитная", callback_data=f"admin_subscription:activate:unlimited:{user_id}")
        ],
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin_subscription:cancel"),
            InlineKeyboardButton(text="❌ Закрыть", callback_data="action:close")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard) 