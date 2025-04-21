#!/bin/bash
set -e

# Проверка существования директории venv
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    # Используем python3, так как на macOS/Linux 'python' может указывать на старую версию
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Ошибка при создании виртуального окружения. Убедитесь, что python3 установлен."
        exit 1
    fi
else
    echo "Виртуальное окружение venv уже существует."
fi

# Активация виртуального окружения и установка зависимостей
echo "Активация виртуального окружения и установка зависимостей..."
source venv/bin/activate

if [ $? -ne 0 ]; then
    echo "Ошибка при активации виртуального окружения."
    exit 1
fi

pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "Ошибка при установке зависимостей из requirements.txt."
    exit 1
fi

# Запуск основного скрипта
echo "Запуск main.py..."
python3 main.py

echo "Скрипт завершил работу." 