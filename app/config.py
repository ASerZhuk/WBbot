import os
import json
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла (если он существует)
load_dotenv()

# Токен бота
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'ваш_токен_бота')

# Конфигурация веб-сервера
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = 3000

# Конфигурация Firebase
FIREBASE_CREDENTIALS = os.environ.get('FIREBASE_CREDENTIALS', 'app/paymentbotwb-firebase-adminsdk-fbsvc-db087d202d.json')
FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID', 'paymentbotwb')

# Если FIREBASE_CREDENTIALS передан как строка JSON, сохраняем во временный файл
if FIREBASE_CREDENTIALS and FIREBASE_CREDENTIALS.startswith('{'):
    try:
        creds_dict = json.loads(FIREBASE_CREDENTIALS)
        temp_path = 'firebase-credentials-temp.json'
        with open(temp_path, 'w') as f:
            json.dump(creds_dict, f)
        FIREBASE_CREDENTIALS = temp_path
    except json.JSONDecodeError:
        pass  # Не JSON строка, используем как есть (путь к файлу)

# Конфигурация ЮMoney
YOOMONEY_WALLET = "4100117527556990"
YOOMONEY_AMOUNT = 100.00

# URL для webhook
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST', 'https://wb-review-bot.onrender.com')
WEBHOOK_PATH = '/webhook/telegram'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
