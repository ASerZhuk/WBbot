import threading
import time
import schedule
from datetime import datetime, timedelta
from firebase_manager import FirebaseManager
from bot import bot

firebase_manager = FirebaseManager()

def remind_inactive_users():
    """Отправляет напоминания неактивным пользователям"""
    # Получаем пользователей, которые не использовали бота более 7 дней
    inactive_users = firebase_manager.get_inactive_users(days=7)
    
    for user in inactive_users:
        user_id = user.get('user_id')
        attempts = user.get('attempts', 0)
        
        if attempts > 0:
            # Пользователь имеет попытки, но не использует их
            try:
                bot.send_message(
                    user_id,
                    f"👋 Привет! Мы заметили, что вы давно не пользовались нашим ботом.\n\n"
                    f"У вас осталось {attempts} неиспользованных попыток анализа. "
                    f"Не упустите возможность проанализировать отзывы на интересующие вас товары!"
                )
            except Exception:
                pass
        else:
            # У пользователя нет попыток
            try:
                markup = types.InlineKeyboardMarkup()
                payment_button = types.InlineKeyboardButton(
                    "💳 Пополнить попытки",
                    url=payment_manager.create_payment_link(user_id)
                )
                markup.add(payment_button)
                
                bot.send_message(
                    user_id,
                    "👋 Привет! Мы заметили, что вы давно не пользовались нашим ботом.\n\n"
                    "У вас закончились попытки анализа. Пополните их, чтобы продолжить "
                    "пользоваться всеми возможностями бота!",
                    reply_markup=markup
                )
            except Exception:
                pass

def run_scheduler():
    """Запускает планировщик задач"""
    # Напоминания каждый день в 12:00
    schedule.every().day.at("12:00").do(remind_inactive_users)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# Запускаем планировщик в отдельном потоке
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start() 