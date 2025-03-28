import requests
import logging
from config import BOT_TOKEN, WEBHOOK_HOST

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def set_webhook():
    """Устанавливает webhook для Telegram бота"""
    webhook_url = f"{WEBHOOK_HOST}/webhook/{BOT_TOKEN}"
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}"
    
    try:
        response = requests.get(api_url)
        logger.info(f"Setting webhook to {webhook_url}")
        logger.info(f"Response: {response.json()}")
        return response.json()
    except Exception as e:
        logger.error(f"Error setting webhook: {str(e)}")
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    set_webhook() 