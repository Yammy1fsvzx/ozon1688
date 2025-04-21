@echo off

REM Проверка существования директории venv
IF NOT EXIST venv (
    echo Создание виртуального окружения...
    python -m venv venv
    IF %ERRORLEVEL% NEQ 0 (
        echo Ошибка при создании виртуального окружения. Убедитесь, что Python установлен и доступен в PATH.
        exit /b 1
    )
) ELSE (
    echo Виртуальное окружение venv уже существует.
)

REM Активация виртуального окружения и установка зависимостей
echo Активация виртуального окружения и установка зависимостей...
CALL .\venv\Scripts\activate.bat

IF %ERRORLEVEL% NEQ 0 (
    echo Ошибка при активации виртуального окружения.
    exit /b 1
)

pip install -r requirements.txt

IF %ERRORLEVEL% NEQ 0 (
    echo Ошибка при установке зависимостей из requirements.txt.
    exit /b 1
)

REM Запуск основного скрипта
echo Запуск main.py...
python main.py

echo Скрипт завершил работу.
pause 