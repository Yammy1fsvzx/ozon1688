#!/usr/bin/env python
# -*- coding: utf-8 -*-

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_reprocess_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для повторной обработки товара
    
    :param task_id: ID задачи
    :return: InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да",
                    callback_data=f"reprocess:yes:{task_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"reprocess:no:{task_id}"
                )
            ]
        ]
    )

def get_main_keyboard() -> InlineKeyboardMarkup:
    """
    Создает основную клавиатуру с inline-кнопками
    
    :return: InlineKeyboardMarkup
    """
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Получить отчет", callback_data="action:report"),
            InlineKeyboardButton(text="📈 Статистика", callback_data="action:stats")
        ],
        [
            InlineKeyboardButton(text="🔄 Активные задачи", callback_data="action:active"),
            InlineKeyboardButton(text="❓ Помощь", callback_data="action:help")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard) 