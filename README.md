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

### Вариант 1: Локальная установка

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

### Вариант 2: Установка через Docker

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/Ozon1688.git
cd Ozon1688
```

2. Создайте файл `.env` в корневой директории проекта и добавьте в него:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

3. Запустите приложение через Docker Compose:
```bash
docker-compose up -d
```

## Использование

### Локальный запуск

1. Запустите бота:
```bash
python src/main.py
```

### Docker

1. Запуск:
```bash
docker-compose up -d
```

2. Остановка:
```bash
docker-compose down
```

3. Просмотр логов:
```bash
docker-compose logs -f
```

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
│   └── utils/
│       ├── logger.py
│       ├── utils.py
│       └── excel_generator.py
│
├── logs/           # Директория для логов
├── requirements.txt
├── .env
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── README.md
└── main.py
```

## Лицензия

MIT 