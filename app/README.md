# WB Review Bot

Telegram бот для анализа отзывов на товары с Wildberries.

## Настройка окружения

Для работы бота необходимо настроить следующие переменные окружения:

- `BOT_TOKEN` - токен Telegram бота
- `FIREBASE_CREDENTIALS` - JSON с учетными данными Firebase (сервисный аккаунт)
- `FIREBASE_PROJECT_ID` - ID проекта Firebase
- `WEBHOOK_HOST` - URL для webhook (например, https://wb-review-bot.onrender.com)

## Локальная разработка

1. Создайте файл `.env` в папке app со следующим содержимым: 