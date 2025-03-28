from flask import Flask, request, jsonify, redirect, render_template
from flask_cors import CORS  # Добавляем импорт CORS
from bot import bot, firebase_manager, payment_manager
from config import WEBAPP_HOST, WEBAPP_PORT, BOT_TOKEN, WEBHOOK_HOST, WEBHOOK_PATH
import telebot
import os
import logging
from pathlib import Path  # Добавим для лучшей работы с путями
from importlib import reload
import config

# Перезагружаем конфиг для обновления значений
reload(config)

# Настраиваем более подробное логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем абсолютный путь к текущей директории
BASE_DIR = Path(__file__).resolve().parent
# Путь к папке templates
template_dir = BASE_DIR / 'templates'

# Создаем папку templates, если её нет
template_dir.mkdir(exist_ok=True)
logger.info(f"Template directory: {template_dir}")

# Шаблоны для страниц
TEMPLATES = {
    'test.html': '''<!DOCTYPE html>
<html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Test Page</title>
    </head>
    <body style="text-align: center; padding: 50px">
        <h1>{{ message }}</h1>
        <p>Bot username: @{{ bot_username }}</p>
    </body>
</html>
''',
    'error.html': '''<!DOCTYPE html>
<html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Ошибка {{ error_code }}</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f5f5f5;
            }
            .container {
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                max-width: 400px;
            }
            .error-code {
                font-size: 48px;
                color: #e74c3c;
                margin-bottom: 20px;
            }
            .error-message {
                color: #666;
                margin-bottom: 25px;
            }
            .button {
                background-color: #0088cc;
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
                text-decoration: none;
                transition: background-color 0.3s;
            }
            .button:hover {
                background-color: #006699;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-code">{{ error_code }}</div>
            <p class="error-message">{{ error_message }}</p>
            <a href="https://t.me/{{bot_username}}" class="button">Вернуться в бот</a>
        </div>
    </body>
</html>
''',
    'payment_success.html': '''<!DOCTYPE html>
<html lang="ru">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Оплата успешна</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background-color: #f5f5f5;
            }
            .container {
                text-align: center;
                padding: 40px;
                background: white;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                max-width: 400px;
            }
            .success-icon {
                color: #4caf50;
                font-size: 48px;
                margin-bottom: 20px;
            }
            .title {
                color: #333;
                margin-bottom: 15px;
            }
            .message {
                color: #666;
                margin-bottom: 25px;
            }
            .button {
                background-color: #0088cc;
                color: white;
                padding: 12px 24px;
                border-radius: 5px;
                text-decoration: none;
                transition: background-color 0.3s;
            }
            .button:hover {
                background-color: #006699;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="success-icon">✅</div>
            <h1 class="title">Оплата успешно выполнена!</h1>
            <p class="message">Вам начислено 10 новых попыток анализа.</p>
            <a href="https://t.me/{{bot_username}}" class="button">Вернуться в бот</a>
        </div>
    </body>
</html>
'''
}

# Проверяем и создаем шаблоны
for template_name, template_content in TEMPLATES.items():
    template_path = template_dir / template_name
    if not template_path.exists():
        template_path.write_text(template_content, encoding='utf-8')
        logger.info(f"Created template: {template_name}")
    else:
        logger.info(f"Template exists: {template_name}")

# Инициализируем Flask с поддержкой CORS
app = Flask(
    __name__,
    template_folder=str(template_dir.absolute()),
    static_folder=str(BASE_DIR / 'static')
)
CORS(app)  # Включаем CORS для всех маршрутов

# Добавляем конфигурацию в контекст приложения
app.config.update(
    WEBHOOK_HOST=config.WEBHOOK_HOST,
    WEBHOOK_URL=config.WEBHOOK_URL
)

# Настройка webhook
WEBHOOK_URL_BASE = WEBHOOK_HOST
WEBHOOK_URL_PATH = WEBHOOK_PATH

@app.before_request
def log_request_info():
    """Логируем информацию о каждом запросе"""
    logger.info('Headers: %s', request.headers)
    logger.info('Body: %s', request.get_data())
    logger.info('Path: %s', request.path)

@app.route('/')
def index():
    """Корневой маршрут"""
    logger.info("Accessing root route")
    return "WB Review Bot is running!"

@app.route('/test')
def test():
    """Тестовый маршрут"""
    try:
        logger.debug("Accessing test route")
        logger.debug(f"Template folder: {app.template_folder}")
        logger.debug(f"Available templates: {os.listdir(template_dir)}")
        
        bot_info = bot.get_me()
        logger.debug(f"Bot info: {bot_info}")
        
        return render_template(
            'test.html',
            message="Bot server is running!",
            bot_username=bot_info.username
        )
    except Exception as e:
        logger.error(f"Error in test route: {str(e)}", exc_info=True)
        return f"Error: {str(e)}", 500

@app.route('/status')
def status():
    """Проверка статуса сервера"""
    try:
        bot_info = bot.get_me()
        response = {
            'status': 'ok',
            'bot_username': bot_info.username,
            'server': 'running',
            'template_dir_exists': os.path.exists(template_dir),
            'templates': os.listdir(template_dir) if os.path.exists(template_dir) else []
        }
        logger.info(f"Status check: {response}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'template_dir': template_dir
        }), 500

@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'status': 'error', 'message': 'Invalid content type'})

@app.route('/webhook/payment', methods=['POST'])
def payment_webhook():
    """Обработка уведомлений об оплате"""
    try:
        # Получаем данные уведомления
        notification_data = request.json

        # Проверяем платеж
        is_valid, user_id = payment_manager.verify_payment(notification_data)
        
        if is_valid and user_id:
            # Начисляем попытки пользователю
            firebase_manager.add_attempts(user_id)
            
            # Отправляем уведомление пользователю
            bot.send_message(
                user_id,
                "✅ Оплата успешно получена!\n"
                "Вам начислено 10 новых попыток анализа."
            )
            return jsonify({'status': 'success'}), 200
        
        return jsonify({'status': 'invalid_payment'}), 400

    except Exception as e:
        print(f"Error processing payment webhook: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/webhook/payment-success', methods=['GET'])
def payment_success():
    user_id = request.args.get('userId')
    label = request.args.get('label')
    
    logger.info(f"Payment webhook called: userId={user_id}, label={label}")
    
    if user_id and label and label.startswith('wb_review_bot_'):
        try:
            # Извлекаем информацию о плане из метки
            parts = label.split('_')
            if len(parts) >= 4:
                user_id = int(parts[3])
                plan = parts[4] if len(parts) >= 5 else 'basic'
                
                # Получаем количество попыток для плана
                attempts = payment_manager.plans.get(plan, {}).get('attempts', 10)
                
                # Добавляем попытки пользователю
                firebase_manager.add_attempts(user_id, attempts)
                
                # Записываем информацию о платеже
                firebase_manager.record_payment(user_id, payment_manager.plans.get(plan, {}).get('amount', 50), plan)
                
                logger.info(f"Payment successful: User {user_id}, Plan {plan}, Attempts {attempts}")
                
                # Отправляем уведомление пользователю
                try:
                    bot.send_message(
                        user_id,
                        f"✅ Оплата успешно выполнена!\n\n"
                        f"Вам начислено {attempts} попыток анализа.\n"
                        f"Спасибо за поддержку бота!"
                    )
                except Exception as e:
                    logger.error(f"Error sending payment notification: {str(e)}")
                
                # Перенаправляем на страницу успешной оплаты
                return render_template('payment_success.html', bot_username=bot.get_me().username)
            
        except Exception as e:
            logger.error(f"Error processing payment: {str(e)}")
            return render_template('error.html', error=str(e))
    
    return jsonify({'status': 'error', 'message': 'Invalid payment data'})

# Обработчик 404 ошибки
@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error for path: {request.path}")
    return render_template(
        'error.html',
        error_code=404,
        error_message="Страница не найдена",
        bot_username=bot.get_me().username
    ), 404

# Добавим тестовый маршрут для проверки шаблонов
@app.route('/debug')
def debug():
    """Отладочный маршрут"""
    templates_list = list(template_dir.glob('*.html'))
    return jsonify({
        'base_dir': str(BASE_DIR),
        'template_dir': str(template_dir),
        'templates_exist': template_dir.exists(),
        'templates_list': [t.name for t in templates_list],
        'flask_template_folder': app.template_folder,
        'template_contents': {
            t.name: t.read_text(encoding='utf-8') 
            for t in templates_list
        }
    })

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
        logger.info(f"Webhook set to {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}")
        return jsonify({'status': 'ok', 'message': f'Webhook set to {WEBHOOK_URL_BASE + WEBHOOK_URL_PATH}'})
    except Exception as e:
        logger.error(f"Error setting webhook: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    logger.info("=== Starting server ===")
    logger.info(f"Base directory: {BASE_DIR}")
    logger.info(f"Template directory: {template_dir}")
    logger.info(f"Flask template folder: {app.template_folder}")
    
    # Проверяем наличие шаблонов
    if os.path.exists(template_dir):
        templates = os.listdir(template_dir)
        logger.info(f"Found templates: {templates}")
        
        # Проверяем содержимое test.html
        test_path = os.path.join(template_dir, 'test.html')
        if os.path.exists(test_path):
            with open(test_path, 'r', encoding='utf-8') as f:
                logger.debug(f"test.html contents:\n{f.read()}")
    else:
        logger.error(f"Templates directory not found at {template_dir}")
    
    # Определяем порт из переменной окружения или используем 5000 по умолчанию
    port = int(os.environ.get("PORT", 5000))
    
    # Запускаем Flask приложение
    app.run(host="0.0.0.0", port=port) 