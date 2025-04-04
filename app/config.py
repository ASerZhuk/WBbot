import os
import json
import pathlib

# Определяем базовую директорию
BASE_DIR = pathlib.Path(__file__).parent

# Функция для загрузки .env файла (простая замена dotenv)
def load_env_file():
    env_path = BASE_DIR / '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

# Загружаем переменные окружения из .env файла (если он существует)
try:
    load_env_file()
except Exception:
    pass  # Игнорируем ошибки при загрузке .env файла

# Токен бота
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'ваш_токен_бота')

# Конфигурация веб-сервера
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.environ.get('PORT', 5000))

# Конфигурация Firebase
FIREBASE_CREDENTIALS_STR = os.environ.get('FIREBASE_CREDENTIALS')
FIREBASE_PROJECT_ID = os.environ.get('FIREBASE_PROJECT_ID', 'paymentbotwb')

# Если FIREBASE_CREDENTIALS передан как строка JSON, сохраняем во временный файл
if FIREBASE_CREDENTIALS_STR and (FIREBASE_CREDENTIALS_STR.startswith('{') or FIREBASE_CREDENTIALS_STR.startswith('{')):
    try:
        creds_dict = json.loads(FIREBASE_CREDENTIALS_STR)
        temp_path = BASE_DIR / 'firebase-credentials-temp.json'
        with open(temp_path, 'w') as f:
            json.dump(creds_dict, f)
        FIREBASE_CREDENTIALS = str(temp_path)
    except json.JSONDecodeError:
        # Если не удалось декодировать JSON, используем как есть
        FIREBASE_CREDENTIALS = FIREBASE_CREDENTIALS_STR
else:
    # Если переменная не задана, используем локальный файл (для разработки)
    FIREBASE_CREDENTIALS = os.environ.get('FIREBASE_CREDENTIALS', str(BASE_DIR / 'paymentbotwb-firebase-adminsdk-fbsvc-db087d202d.json'))

# Конфигурация ЮMoney
YOOMONEY_WALLET = os.environ.get('YOOMONEY_WALLET', "4100117527556990")
YOOMONEY_AMOUNT = float(os.environ.get('YOOMONEY_AMOUNT', 100.00))

# URL для webhook
WEBHOOK_HOST = os.environ.get('WEBHOOK_HOST', 'https://wbbot-isx8.onrender.com')
WEBHOOK_PATH = '/webhook/' + BOT_TOKEN
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Для совместимости с существующим кодом
WEBHOOK_URL_BASE = WEBHOOK_HOST
WEBHOOK_URL_PATH = WEBHOOK_PATH
