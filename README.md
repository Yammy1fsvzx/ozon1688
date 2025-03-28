# Ozon1688 Bot

Telegram бот для анализа товаров Ozon и поиска аналогов на 1688.com.

## Возможности

- Парсинг товаров с Ozon
- Поиск аналогов на 1688.com
- Расчет прибыльности с учетом всех расходов
- Генерация отчетов в Excel
- Отслеживание статуса обработки
- Статистика по задачам
- Просмотр активных задач

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/Ozon1688.git
cd Ozon1688
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate     # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` в корневой директории проекта и добавьте в него:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

## Использование

1. Запустите бота:
```bash
python src/main.py
```

2. Отправьте боту ссылку на товар с Ozon в одном из форматов:
- https://www.ozon.ru/product/...
- https://ozon.ru/t/...

3. Используйте кнопки меню для:
- Просмотра статистики
- Получения отчета в Excel
- Просмотра активных задач
- Получения справки

## Структура проекта

```
Ozon1688/
├── src/
│   ├── bot/
│   │   ├── telegram_bot.py
│   │   └── keyboards.py
│   ├── core/
│   │   ├── database.py
│   │   └── models.py
│   ├── utils/
│   │   ├── logger.py
│   │   ├── utils.py
│   │   └── excel_generator.py
│   └── main.py
├── requirements.txt
├── .env
└── README.md
```

## Лицензия

MIT 