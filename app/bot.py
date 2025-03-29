import telebot
import json
import requests
import re
import g4f
from telebot import types
from firebase_manager import FirebaseManager
from payment_manager import PaymentManager
from config import BOT_TOKEN
import logging
from functools import lru_cache
from datetime import datetime
import os

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Инициализация менеджеров
firebase_manager = FirebaseManager()
payment_manager = PaymentManager()

# Список ID администраторов
ADMIN_IDS = [1312244058]  # Убедитесь, что это ваш ID

# Словари с переводами
TRANSLATIONS = {
    'ru': {
        'welcome': "👋 Привет! Я бот для анализа товаров на Wildberries.\n\n"
                   "🔍 Отправь мне ссылку на товар с Wildberries или артикул товара, "
                   "и я проанализирую отзывы, чтобы выделить основные плюсы и минусы товара.\n\n"
                   "💡 Используй /help для получения справки и /refer для приглашения друзей.",
        'help': "🤖 Как пользоваться ботом:\n\n"
                "1️⃣ Отправьте мне ссылку на товар с Wildberries или просто артикул товара\n"
                "2️⃣ Я проанализирую отзывы и выделю основные плюсы и минусы\n"
                "3️⃣ Каждый анализ расходует 1 попытку\n\n"
                "💰 Когда попытки закончатся, вы сможете приобрести дополнительные\n\n"
                "❓ Если у вас возникли вопросы или проблемы, напишите @ваш_контакт",
        # ... другие переводы
    },
    'en': {
        'welcome': "👋 Hello! I'm a bot for analyzing Wildberries products.\n\n"
                   "🔍 Send me a link to a product on Wildberries or the product's SKU, "
                   "and I'll analyze the reviews to highlight the main pluses and minuses of the product.\n\n"
                   "💡 Use /help for help and /refer to invite friends.",
        'help': "🤖 How to use the bot:\n\n"
                "1️⃣ Send me a link to a product on Wildberries or simply the product's SKU\n"
                "2️⃣ I'll analyze the reviews and highlight the main pluses and minuses\n"
                "3️⃣ Each analysis consumes 1 attempt\n\n"
                "💰 When your attempts run out, you can purchase additional\n\n"
                "❓ If you have any questions or problems, write @your_contact",
        # ... другие переводы
    }
}

class WbReview:
    def __init__(self, string: str):
        self.sku = self.get_sku(string=string)
        self.item_name = None  # Инициализируем как None
        self.root_id = None
        # Получаем root_id и item_name
        self.get_root_id()

    @staticmethod
    def get_sku(string: str) -> str:
        """Получение артикула"""
        if "wildberries" in string:
            pattern = r"\d{7,15}"
            sku = re.findall(pattern, string)
            if sku:
                return sku[0]
            else:
                raise Exception("Не удалось найти артикул")
        return string

    def get_root_id(self):
        """Получение id родителя и названия товара"""
        try:
            response = requests.get(
                f'https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-8144334&spp=30&nm={self.sku}',
                headers={'User-Agent': 'Mozilla/5.0'},
            )
            if response.status_code != 200:
                raise Exception("Не удалось определить id родителя")
            
            data = response.json()
            if not data.get("data") or not data["data"].get("products") or len(data["data"]["products"]) == 0:
                raise Exception("Товар не найден")
            
            product = data["data"]["products"][0]
            self.item_name = product.get("name", "Название не найдено")
            self.root_id = product.get("root")
            if not self.root_id:
                raise Exception("Не удалось получить root_id товара")
            return self.root_id
        except Exception as e:
            logging.error(f"Error in get_root_id: {str(e)}")
            raise Exception(f"Ошибка при получении информации о товаре: {str(e)}")

    def get_review(self) -> json:
        """Получение отзывов"""
        if not self.root_id:
            raise Exception("root_id не установлен")
            
        try:
            response = requests.get(f'https://feedbacks1.wb.ru/feedbacks/v1/{self.root_id}', 
                                  headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                if not response.json()["feedbacks"]:
                    raise Exception("Сервер 1 не подошел")
                return response.json()
        except Exception:
            response = requests.get(f'https://feedbacks2.wb.ru/feedbacks/v1/{self.root_id}', 
                                  headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                return response.json()

    def parse(self):
        json_feedbacks = self.get_review()
        if not json_feedbacks:
            return []
        
        # Получаем все отзывы для данного SKU
        feedbacks = [feedback.get("text") for feedback in json_feedbacks["feedbacks"]
                     if str(feedback.get("nmId")) == self.sku]
        
        # Сортируем отзывы по длине, чтобы получать стабильный результат
        feedbacks.sort(key=len, reverse=True)
        
        # Ограничиваем количество отзывов для анализа
        if len(feedbacks) > 80:
            feedbacks = feedbacks[:80]
        
        return feedbacks

@lru_cache(maxsize=100)
def analyze_reviews_cached(sku, reviews_text):
    """Кэшированная версия анализа отзывов с учетом артикула товара"""
    return analyze_reviews(reviews_text.split("\n"))

def analyze_reviews(reviews_list):
    """Анализирует отзывы с помощью G4F"""
    reviews_text = "\n\n".join(reviews_list)
    prompt = f"""
    На основе следующих отзывов с Wildberries сделай подробный анализ товара.
    Отзывы:
    {reviews_text}
    
    Пожалуйста, структурируй ответ следующим образом:
    
    ✅ ПЛЮСЫ ТОВАРА:
    - [перечисли кратко основные плюсы, которые часто упоминаются в отзывах, тезисно]

    ❌ МИНУСЫ ТОВАРА:
    - [перечисли кратко основные минусы и недостатки из отзывов, тезисно]
    
    💡 РЕКОМЕНДАЦИИ:
    - [дай 2-3 рекомендации потенциальным покупателям]

    📝 ОБЩИЙ ВЫВОД:
    [краткое заключение о товаре в 1-2 предложения]
    
    Пожалуйста, не добавляй никаких ссылок или рекламы в ответ.
    """
    
    models = ["gpt-3.5-turbo", "gpt-4", "claude-v2", "gemini-pro"]
    
    for model in models:
        try:
            response = g4f.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=30  # Добавляем таймаут
            )
            # Удаляем рекламные ссылки из ответа
            cleaned_response = re.sub(r'https?://\S+', '', response)
            return cleaned_response.strip()
        except Exception as e:
            logging.error(f"Error with model {model}: {str(e)}")
            continue
    
    return "Не удалось выполнить анализ отзывов. Пожалуйста, попробуйте позже."

def get_user_language(user_id):
    """Получает язык пользователя из базы данных"""
    return firebase_manager.get_user_language(user_id) or 'ru'

def get_text(key, user_id):
    """Возвращает текст на языке пользователя"""
    lang = get_user_language(user_id)
    return TRANSLATIONS.get(lang, TRANSLATIONS['ru']).get(key, TRANSLATIONS['ru'][key])

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    text = message.text
    
    # Проверяем наличие реферального кода
    if len(text.split()) > 1 and text.split()[1].startswith('ref'):
        try:
            referrer_id = int(text.split()[1][3:])
            if referrer_id != user_id:  # Проверка, что пользователь не приглашает сам себя
                firebase_manager.add_referral(referrer_id, user_id)
                bot.send_message(
                    referrer_id,
                    f"🎉 Поздравляем! По вашей ссылке зарегистрировался новый пользователь.\n"
                    f"Вам начислено +2 бесплатные попытки анализа!"
                )
        except Exception as e:
            logging.error(f"Error processing referral: {str(e)}")
    
    # Создаем клавиатуру с основными функциями
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    analyze_button = types.InlineKeyboardButton("🔍 Анализ товара", callback_data="menu_analyze")
    stats_button = types.InlineKeyboardButton("📊 Моя статистика", callback_data="menu_stats")
    refer_button = types.InlineKeyboardButton("👥 Пригласить друзей", callback_data="menu_refer")
    help_button = types.InlineKeyboardButton("❓ Помощь", callback_data="menu_help")
    
    # Добавляем кнопку админки только для администраторов
    if user_id in ADMIN_IDS:
        admin_button = types.InlineKeyboardButton("🔧 Админ-панель", callback_data="menu_admin")
        markup.add(analyze_button, stats_button, refer_button, help_button, admin_button)
    else:
        markup.add(analyze_button, stats_button, refer_button, help_button)
    
    bot.reply_to(message, 
        "👋 Привет! Я бот для анализа товаров на Wildberries.\n\n"
        "🔍 Отправь мне ссылку на товар с Wildberries или артикул товара, "
        "и я проанализирую отзывы, чтобы выделить основные плюсы и минусы товара.\n\n"
        "Или воспользуйся меню ниже:",
        reply_markup=markup
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    user_id = message.from_user.id
    bot.reply_to(message, get_text('help', user_id))

@bot.message_handler(commands=['stats'])
def send_stats(message):
    user_id = message.from_user.id
    user_stats = firebase_manager.get_user_stats(user_id)
    
    stats_message = (
        "📊 *Ваша статистика*\n\n"
        f"🔍 Всего анализов: {user_stats.get('total_attempts_used', 0)}\n"
        f"💰 Всего оплачено попыток: {user_stats.get('total_purchased', 0)}\n"
        f"⏱ Первое использование: {user_stats.get('created_at_formatted', 'Неизвестно')}\n"
        f"🔄 Последнее использование: {user_stats.get('last_used_formatted', 'Неизвестно')}\n\n"
        f"Осталось попыток: {user_stats.get('attempts', 0)}"
    )
    
    bot.reply_to(message, stats_message, parse_mode="Markdown")

@bot.message_handler(commands=['refer'])
def send_referral(message):
    user_id = message.from_user.id
    referral_link = f"https://t.me/{bot.get_me().username}?start=ref{user_id}"
    
    markup = types.InlineKeyboardMarkup()
    share_button = types.InlineKeyboardButton(
        "Поделиться ботом",
        url=f"https://t.me/share/url?url={referral_link}&text=Попробуй%20этот%20бот%20для%20анализа%20отзывов%20на%20Wildberries!"
    )
    markup.add(share_button)
    
    bot.reply_to(
        message,
        f"🎁 *Приглашайте друзей и получайте бонусы!*\n\n"
        f"За каждого приглашенного друга вы получите +2 бесплатные попытки анализа.\n\n"
        f"Ваша реферальная ссылка:\n`{referral_link}`\n\n"
        f"Уже приглашено: {firebase_manager.get_referral_count(user_id)} чел.",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.message_handler(commands=['admin'])
def admin_command(message):
    user_id = message.from_user.id
    logging.info(f"Admin command received from user {user_id}. Admin IDs: {ADMIN_IDS}")
    
    # Проверка, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        logging.warning(f"User {user_id} tried to access admin panel but is not in ADMIN_IDS")
        bot.reply_to(message, "⛔ У вас нет доступа к этой команде.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        # Если команда вызвана без аргументов, показываем справку
        bot.reply_to(message, 
            "🔧 *Админ-панель*\n\n"
            "Доступные команды:\n"
            "/admin stats - общая статистика\n"
            "/admin user [ID] - информация о пользователе\n"
            "/admin add [ID] [количество] - добавить попытки\n"
            "/admin broadcast [текст] - отправить сообщение всем",
            parse_mode="Markdown"
        )
        return
    
    command = args[1]
    
    # Обработка команды "stats" - показывает общую статистику
    if command == "stats":
        stats = firebase_manager.get_admin_stats()
        bot.reply_to(message,
            f"📊 *Общая статистика*\n\n"
            f"👥 Всего пользователей: {stats['total_users']}\n"
            f"🔍 Всего анализов: {stats['total_attempts_used']}\n"
            f"💰 Всего оплат: {stats['total_payments']}\n"
            f"💵 Общая сумма: {stats['total_amount']}₽",
            parse_mode="Markdown"
        )
    
    # Обработка команды "user" - показывает информацию о конкретном пользователе
    elif command == "user" and len(args) > 2:
        try:
            target_user_id = int(args[2])
            user_info = firebase_manager.get_user_stats(target_user_id)
            
            if not user_info:
                bot.reply_to(message, f"❌ Пользователь с ID {target_user_id} не найден.")
                return
            
            bot.reply_to(message,
                f"👤 *Информация о пользователе*\n\n"
                f"ID: {target_user_id}\n"
                f"Попыток: {user_info.get('attempts', 0)}\n"
                f"Всего использовано: {user_info.get('total_attempts_used', 0)}\n"
                f"Всего куплено: {user_info.get('total_purchased', 0)}\n"
                f"Создан: {user_info.get('created_at_formatted', 'Неизвестно')}\n"
                f"Последнее использование: {user_info.get('last_used_formatted', 'Никогда')}",
                parse_mode="Markdown"
            )
        except ValueError:
            bot.reply_to(message, "❌ Некорректный ID пользователя.")
    
    # Обработка команды "add" - добавляет попытки пользователю
    elif command == "add" and len(args) > 3:
        try:
            target_user_id = int(args[2])
            amount = int(args[3])
            
            if amount <= 0:
                bot.reply_to(message, "❌ Количество попыток должно быть положительным числом.")
                return
            
            firebase_manager.add_attempts(target_user_id, amount)
            bot.reply_to(message, f"✅ Пользователю {target_user_id} добавлено {amount} попыток.")
        except ValueError:
            bot.reply_to(message, "❌ Некорректные параметры команды.")
    
    # Обработка команды "broadcast" - отправляет сообщение всем пользователям
    elif command == "broadcast" and len(args) > 2:
        broadcast_text = " ".join(args[2:])
        users = firebase_manager.get_all_users()
        sent_count = 0
        failed_count = 0
        
        # Отправляем сообщение о начале рассылки
        status_msg = bot.reply_to(message, f"⏳ Начинаю рассылку {len(users)} пользователям...")
        
        for user in users:
            try:
                user_id = user.get('user_id')
                if user_id:
                    bot.send_message(user_id, broadcast_text)
                    sent_count += 1
                    
                    # Обновляем статус каждые 10 отправленных сообщений
                    if sent_count % 10 == 0:
                        bot.edit_message_text(
                            f"⏳ Отправлено: {sent_count}/{len(users)}...",
                            chat_id=status_msg.chat.id,
                            message_id=status_msg.message_id
                        )
            except Exception as e:
                logging.error(f"Error sending broadcast to {user.get('user_id')}: {str(e)}")
                failed_count += 1
        
        # Обновляем сообщение с финальным статусом
        bot.edit_message_text(
            f"✅ Рассылка завершена!\n\n"
            f"✓ Успешно отправлено: {sent_count}\n"
            f"✗ Ошибок: {failed_count}\n"
            f"📊 Всего пользователей: {len(users)}",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
    
    else:
        bot.reply_to(message, "❌ Неизвестная команда. Используйте /admin для справки.")

@bot.message_handler(commands=['cancel'])
def cancel_operation(message):
    """Отмена текущей операции"""
    user_id = message.from_user.id
    # Здесь можно добавить логику для отмены операций
    bot.reply_to(message, "🚫 Текущая операция отменена.")

@bot.message_handler(commands=['feedback'])
def feedback_command(message):
    """Команда для отправки отзыва разработчикам"""
    user_id = message.from_user.id
    
    # Запрашиваем отзыв
    msg = bot.reply_to(message, 
        "📝 Пожалуйста, напишите ваш отзыв или предложение в одном сообщении.\n"
        "Мы ценим ваше мнение и учтем его при улучшении бота!"
    )
    
    # Регистрируем следующий шаг
    bot.register_next_step_handler(msg, process_feedback)

def process_feedback(message):
    """Обработка полученного отзыва"""
    user_id = message.from_user.id
    feedback_text = message.text
    
    # Сохраняем отзыв в базе данных
    firebase_manager.save_feedback(user_id, feedback_text)
    
    # Отправляем уведомление администраторам
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📨 *Новый отзыв*\n\n"
                f"От: {message.from_user.username or message.from_user.first_name} (ID: {user_id})\n\n"
                f"{feedback_text}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    
    # Благодарим пользователя
    bot.reply_to(message, 
        "🙏 Спасибо за ваш отзыв! Мы обязательно его рассмотрим.\n"
        "В благодарность вам начислена 1 бесплатная попытка анализа."
    )
    
    # Начисляем бонусную попытку
    firebase_manager.add_attempts(user_id, 1)

@bot.message_handler(commands=['language'])
def language_command(message):
    """Команда для изменения языка"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    ru_button = types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")
    en_button = types.InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    markup.add(ru_button, en_button)
    
    bot.reply_to(
        message,
        "🌐 Выберите язык / Choose language:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def language_callback(call):
    """Обработка выбора языка"""
    user_id = call.from_user.id
    lang = call.data.split('_')[1]
    
    firebase_manager.set_user_language(user_id, lang)
    
    if lang == 'ru':
        response = "✅ Язык изменен на русский"
    else:
        response = "✅ Language changed to English"
    
    bot.edit_message_text(
        response,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        logger.info(f"Received message: {message.text}")
        
        # Временное решение для отладки
        bot.reply_to(message, f"Получено сообщение: {message.text}\nНачинаю обработку...")
        
        # Проверка на артикул или ссылку
        if is_wildberries_link(message.text):
            logger.info("Message is a Wildberries link")
            # Логика обработки ссылки
            process_wildberries_link(message)
        elif is_article_number(message.text):
            logger.info("Message is an article number")
            # Логика обработки артикула
            process_article_number(message)
        else:
            logger.info("Message is neither a link nor an article number")
            # Другие сообщения
            bot.reply_to(message, "Отправьте мне ссылку на товар или артикул с Wildberries.")
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}", exc_info=True)
        bot.reply_to(message, "Произошла ошибка при обработке сообщения. Попробуйте позже.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('pay_'))
def handle_payment_callback(call):
    user_id = call.from_user.id
    plan = call.data.split('_')[1]
    
    payment_link = payment_manager.create_payment_link(user_id, plan)
    
    markup = types.InlineKeyboardMarkup()
    pay_button = types.InlineKeyboardButton(
        f"Перейти к оплате",
        url=payment_link
    )
    markup.add(pay_button)
    
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    
    bot.answer_callback_query(call.id)

@bot.inline_handler(lambda query: len(query.query) > 0)
def inline_query(query):
    try:
        # Проверяем, является ли запрос артикулом или ссылкой
        text = query.query
        is_valid_wb = text.isdigit() or ('wildberries' in text.lower() and 'catalog' in text.lower())
        
        if not is_valid_wb:
            return
        
        # Получаем информацию о товаре
        review_handler = WbReview(text)
        
        # Создаем результат
        result = types.InlineQueryResultArticle(
            id='1',
            title=f"Анализ отзывов: {review_handler.item_name}",
            description=f"Артикул: {review_handler.sku}",
            input_message_content=types.InputTextMessageContent(
                message_text=f"🔍 Анализ отзывов для товара:\n{review_handler.item_name}\n\nАртикул: {review_handler.sku}"
            ),
            thumb_url="https://example.com/icon.png",  # Замените на реальную иконку
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(
                    "Получить анализ",
                    url=f"https://t.me/{bot.get_me().username}?start=analyze_{review_handler.sku}"
                )
            )
        )
        
        bot.answer_inline_query(query.id, [result])
    except Exception as e:
        logging.error(f"Error in inline query: {str(e)}")

def track_analytics(user_id, action, details=None):
    """Отслеживание действий пользователя для аналитики"""
    analytics_data = {
        'user_id': user_id,
        'action': action,
        'timestamp': datetime.now()
    }
    
    if details:
        analytics_data.update(details)
    
    try:
        firebase_manager.db.collection('analytics').add(analytics_data)
    except Exception as e:
        logging.error(f"Error tracking analytics: {str(e)}")

@bot.message_handler(commands=['export'])
def export_command(message):
    """Команда для экспорта последних результатов анализа"""
    user_id = message.from_user.id
    
    # Получаем последний анализ пользователя
    last_analysis = firebase_manager.get_last_analysis(user_id)
    
    if not last_analysis:
        bot.reply_to(message, "У вас еще нет сохраненных анализов. Отправьте ссылку на товар для анализа.")
        return
    
    # Создаем текстовый файл с результатами
    analysis_text = (
        f"Анализ отзывов для товара: {last_analysis.get('item_name')}\n"
        f"Артикул: {last_analysis.get('sku')}\n"
        f"Дата анализа: {last_analysis.get('created_at_formatted')}\n\n"
        f"{last_analysis.get('analysis_text')}"
    )
    
    # Отправляем файл
    with open(f"analysis_{user_id}.txt", "w", encoding="utf-8") as file:
        file.write(analysis_text)
    
    with open(f"analysis_{user_id}.txt", "rb") as file:
        bot.send_document(
            user_id,
            file,
            caption="📊 Результаты анализа отзывов"
        )
    
    # Удаляем временный файл
    os.remove(f"analysis_{user_id}.txt")

@bot.message_handler(commands=['compare'])
def compare_command(message):
    """Команда для сравнения двух товаров"""
    user_id = message.from_user.id
    
    # Проверяем количество попыток
    attempts = firebase_manager.get_user_attempts(user_id)
    if attempts < 2:
        bot.reply_to(
            message, 
            f"❌ Для сравнения товаров требуется минимум 2 попытки. У вас осталось: {attempts}."
        )
        return
    
    # Запрашиваем первый товар
    msg = bot.reply_to(
        message,
        "🔍 Пожалуйста, отправьте ссылку или артикул первого товара для сравнения."
    )
    
    # Регистрируем следующий шаг
    bot.register_next_step_handler(msg, process_first_product)

def process_first_product(message):
    """Обработка первого товара для сравнения"""
    user_id = message.from_user.id
    text = message.text
    
    # Проверка на ссылку или артикул
    is_valid_wb = text.isdigit() or ('wildberries' in text.lower() and 'catalog' in text.lower())
    
    if not is_valid_wb:
        bot.reply_to(message, "❌ Пожалуйста, отправьте корректную ссылку на товар с Wildberries или артикул товара.")
        return
    
    # Сохраняем первый товар
    firebase_manager.set_comparison_product(user_id, 1, text)
    
    # Запрашиваем второй товар
    msg = bot.reply_to(
        message,
        "🔍 Теперь отправьте ссылку или артикул второго товара для сравнения."
    )
    
    # Регистрируем следующий шаг
    bot.register_next_step_handler(msg, process_second_product)

def process_second_product(message):
    """Обработка второго товара и выполнение сравнения"""
    user_id = message.from_user.id
    text = message.text
    
    # Проверка на ссылку или артикул
    is_valid_wb = text.isdigit() or ('wildberries' in text.lower() and 'catalog' in text.lower())
    
    if not is_valid_wb:
        bot.reply_to(message, "❌ Пожалуйста, отправьте корректную ссылку на товар с Wildberries или артикул товара.")
        return
    
    # Сохраняем второй товар
    firebase_manager.set_comparison_product(user_id, 2, text)
    
    # Получаем оба товара
    product1 = firebase_manager.get_comparison_product(user_id, 1)
    product2 = firebase_manager.get_comparison_product(user_id, 2)
    
    # Отправляем сообщение о начале сравнения
    processing_msg = bot.reply_to(
        message, 
        f"⏳ Сравниваю товары... Это может занять некоторое время."
    )
    
    try:
        # Анализируем оба товара
        review_handler1 = WbReview(product1)
        reviews1 = review_handler1.parse()
        
        review_handler2 = WbReview(product2)
        reviews2 = review_handler2.parse()
        
        if not reviews1 or not reviews2:
            bot.edit_message_text(
                "❌ Не найдено отзывов для одного из товаров", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id
            )
            return
        
        # Анализируем отзывы обоих товаров
        reviews_text1 = "\n".join(reviews1)
        analysis1 = analyze_reviews_cached(review_handler1.sku, reviews_text1)
        
        reviews_text2 = "\n".join(reviews2)
        analysis2 = analyze_reviews_cached(review_handler2.sku, reviews_text2)
        
        # Сравниваем товары
        comparison = compare_products(review_handler1, review_handler2, analysis1, analysis2)
        
        # Уменьшаем количество попыток (2 попытки за сравнение)
        firebase_manager.decrease_attempts(user_id)
        firebase_manager.decrease_attempts(user_id)
        
        # Отправляем результат
        bot.edit_message_text(
            comparison,
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ Произошла ошибка при сравнении товаров: {str(e)}", 
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

def compare_products(product1, product2, analysis1, analysis2):
    """Сравнение двух товаров на основе их анализов"""
    return (
        f"📊 *Сравнение товаров*\n\n"
        f"🔵 *{product1.item_name}* (Артикул: {product1.sku})\n"
        f"🔴 *{product2.item_name}* (Артикул: {product2.sku})\n\n"
        f"*Анализ первого товара:*\n{analysis1}\n\n"
        f"*Анализ второго товара:*\n{analysis2}\n\n"
        f"*Вывод:*\nНа основе анализа отзывов, рекомендуем выбрать товар, который лучше соответствует вашим требованиям."
    )

@bot.message_handler(commands=['search'])
def search_command(message):
    """Команда для поиска популярных товаров в категории"""
    user_id = message.from_user.id
    
    # Запрашиваем категорию
    msg = bot.reply_to(
        message,
        "🔍 Введите название категории товаров для поиска (например, 'смартфоны', 'платья', 'кроссовки')."
    )
    
    # Регистрируем следующий шаг
    bot.register_next_step_handler(msg, process_category_search)

def process_category_search(message):
    """Обработка поиска по категории"""
    user_id = message.from_user.id
    category = message.text.strip()
    
    # Отправляем сообщение о начале поиска
    processing_msg = bot.reply_to(
        message, 
        f"⏳ Ищу популярные товары в категории '{category}'... Это может занять некоторое время."
    )
    
    try:
        # Поиск товаров
        products = search_products_by_category(category)
        
        if not products:
            bot.edit_message_text(
                f"❌ Не найдено товаров в категории '{category}'", 
                chat_id=message.chat.id, 
                message_id=processing_msg.message_id
            )
            return
        
        # Формируем сообщение с результатами
        result_message = f"🛍️ *Популярные товары в категории '{category}'*\n\n"
        
        for i, product in enumerate(products[:5], 1):
            result_message += (
                f"{i}. [{product['name']}](https://www.wildberries.ru/catalog/{product['id']}/detail.aspx)\n"
                f"   Цена: {product['price']}₽\n"
                f"   Рейтинг: {product['rating']}\n\n"
            )
        
        # Создаем клавиатуру с кнопками для анализа
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for i, product in enumerate(products[:5], 1):
            analyze_button = types.InlineKeyboardButton(
                f"Анализ товара #{i}",
                callback_data=f"analyze_{product['id']}"
            )
            markup.add(analyze_button)
        
        # Отправляем результат
        bot.edit_message_text(
            result_message,
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ Произошла ошибка при поиске товаров: {str(e)}", 
            chat_id=message.chat.id,
            message_id=processing_msg.message_id
        )

def search_products_by_category(category: str) -> list:
    """Поиск популярных товаров в категории"""
    try:
        # Формируем запрос к API Wildberries
        search_url = f"https://search.wb.ru/exactmatch/ru/common/v4/search?appType=1&couponsGeo=12,3,18,15,21&curr=rub&dest=-1029256,-102269,-2162196,-1257786&emp=0&lang=ru&locale=ru&pricemarginCoeff=1.0&query={category}&reg=0&regions=68,64,83,4,38,80,33,70,82,86,75,30,69,22,66,31,40,1,48,71&resultset=catalog&sort=popular&spp=0&suppressSpellcheck=false"
        
        response = requests.get(search_url, headers={'User-Agent': 'Mozilla/5.0'})
        
        if response.status_code != 200:
            return []
        
        data = response.json()
        
        if not data.get('data') or not data['data'].get('products'):
            return []
        
        # Преобразуем данные в удобный формат
        products = []
        
        for product in data['data']['products'][:10]:  # Берем первые 10 товаров
            products.append({
                'id': product.get('id', 0),
                'name': product.get('name', 'Без названия'),
                'price': product.get('priceU', 0) / 100,  # Цена в копейках
                'rating': product.get('rating', 0),
                'feedbacks': product.get('feedbacks', 0)
            })
        
        return products
    
    except Exception as e:
        logging.error(f"Error searching products: {str(e)}")
        return []

@bot.callback_query_handler(func=lambda call: call.data.startswith('analyze_'))
def handle_analyze_callback(call):
    """Обработка нажатия на кнопку анализа товара"""
    user_id = call.from_user.id
    product_id = call.data.split('_')[1]
    
    # Проверяем количество попыток
    attempts = firebase_manager.get_user_attempts(user_id)
    if attempts <= 0:
        bot.answer_callback_query(
            call.id,
            "У вас закончились попытки анализа. Пополните их, чтобы продолжить.",
            show_alert=True
        )
        return
    
    # Отправляем сообщение о начале анализа
    bot.edit_message_text(
        f"⏳ Анализирую отзывы товара... Это может занять некоторое время.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    try:
        # Анализируем товар
        review_handler = WbReview(product_id)
        reviews = review_handler.parse()
        
        if not reviews:
            bot.edit_message_text(
                "❌ Не найдено отзывов для данного товара", 
                chat_id=call.message.chat.id, 
                message_id=call.message.message_id
            )
            return
        
        # Анализируем отзывы
        reviews_text = "\n".join(reviews)
        analysis = analyze_reviews_cached(review_handler.sku, reviews_text)
        
        # Уменьшаем количество попыток
        remaining_attempts = firebase_manager.decrease_attempts(user_id)
        
        # Добавляем информацию о товаре и оставшихся попытках
        analysis_with_info = (
            f"🛍️ *{review_handler.item_name}*\n"
            f"📦 Артикул: {review_handler.sku}\n\n"
            f"{analysis}\n\n"
            f"Осталось попыток: {remaining_attempts}"
        )
        
        # Отправляем результат с кнопками
        markup = types.InlineKeyboardMarkup(row_width=2)
        view_button = types.InlineKeyboardButton(
            "🔍 Посмотреть на WB",
            url=f"https://www.wildberries.ru/catalog/{review_handler.sku}/detail.aspx"
        )
        share_button = types.InlineKeyboardButton(
            "📤 Поделиться",
            switch_inline_query=review_handler.sku
        )
        markup.add(view_button, share_button)
        
        bot.edit_message_text(
            analysis_with_info,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.edit_message_text(
            f"❌ Произошла ошибка: {str(e)}", 
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['test_firebase'])
def test_firebase(message):
    user_id = message.from_user.id
    
    try:
        # Проверяем подключение к Firebase
        stats = firebase_manager.get_user_stats(user_id)
        bot.reply_to(message, f"Firebase работает! Ваши попытки: {stats.get('attempts', 0)}")
    except Exception as e:
        bot.reply_to(message, f"Ошибка Firebase: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
def handle_menu_callback(call):
    """Обработка нажатий на кнопки главного меню"""
    user_id = call.from_user.id
    action = call.data.split('_')[1]
    
    if action == "analyze":
        # Запрашиваем ссылку на товар
        msg = bot.send_message(
            call.message.chat.id,
            "🔍 Пожалуйста, отправьте ссылку на товар с Wildberries или артикул товара."
        )
        
    elif action == "stats":
        # Показываем статистику пользователя
        user_stats = firebase_manager.get_user_stats(user_id)
        
        stats_message = (
            "📊 *Ваша статистика*\n\n"
            f"🔍 Всего анализов: {user_stats.get('total_attempts_used', 0)}\n"
            f"💰 Всего оплачено попыток: {user_stats.get('total_purchased', 0)}\n"
            f"⏱ Первое использование: {user_stats.get('created_at_formatted', 'Неизвестно')}\n"
            f"🔄 Последнее использование: {user_stats.get('last_used_formatted', 'Неизвестно')}\n\n"
            f"Осталось попыток: {user_stats.get('attempts', 0)}"
        )
        
        # Создаем кнопку возврата в главное меню
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
        markup.add(back_button)
        
        bot.send_message(
            call.message.chat.id,
            stats_message,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    elif action == "refer":
        # Показываем реферальную ссылку
        referral_link = f"https://t.me/{bot.get_me().username}?start=ref{user_id}"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        share_button = types.InlineKeyboardButton(
            "📤 Поделиться ботом",
            url=f"https://t.me/share/url?url={referral_link}&text=Попробуй%20этот%20бот%20для%20анализа%20отзывов%20на%20Wildberries!"
        )
        back_button = types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
        markup.add(share_button, back_button)
        
        bot.send_message(
            call.message.chat.id,
            f"🎁 *Приглашайте друзей и получайте бонусы!*\n\n"
            f"За каждого приглашенного друга вы получите +2 бесплатные попытки анализа.\n\n"
            f"Ваша реферальная ссылка:\n`{referral_link}`\n\n"
            f"Уже приглашено: {firebase_manager.get_referral_count(user_id)} чел.",
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    elif action == "help":
        # Показываем справку
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
        markup.add(back_button)
        
        bot.send_message(
            call.message.chat.id,
            "🤖 *Как пользоваться ботом:*\n\n"
            "1️⃣ Отправьте мне ссылку на товар с Wildberries или просто артикул товара\n"
            "2️⃣ Я проанализирую отзывы и выделю основные плюсы и минусы\n"
            "3️⃣ Каждый анализ расходует 1 попытку\n\n"
            "💰 Когда попытки закончатся, вы сможете приобрести дополнительные\n\n"
            "❓ Если у вас возникли вопросы или проблемы, напишите @ваш_контакт",
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    elif action == "admin" and user_id in ADMIN_IDS:
        # Показываем админ-панель
        show_admin_panel(call.message)
    
    # Отвечаем на callback, чтобы убрать часы загрузки
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    """Возврат в главное меню"""
    user_id = call.from_user.id
    
    # Создаем клавиатуру с основными функциями
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    analyze_button = types.InlineKeyboardButton("🔍 Анализ товара", callback_data="menu_analyze")
    stats_button = types.InlineKeyboardButton("📊 Моя статистика", callback_data="menu_stats")
    refer_button = types.InlineKeyboardButton("👥 Пригласить друзей", callback_data="menu_refer")
    help_button = types.InlineKeyboardButton("❓ Помощь", callback_data="menu_help")
    
    # Добавляем кнопку админки только для администраторов
    if user_id in ADMIN_IDS:
        admin_button = types.InlineKeyboardButton("🔧 Админ-панель", callback_data="menu_admin")
        markup.add(analyze_button, stats_button, refer_button, help_button, admin_button)
    else:
        markup.add(analyze_button, stats_button, refer_button, help_button)
    
    bot.edit_message_text(
        "Выберите действие из меню ниже:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    
    bot.answer_callback_query(call.id)

def show_admin_panel(message):
    """Показывает админ-панель с кнопками"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    stats_button = types.InlineKeyboardButton("📊 Общая статистика", callback_data="admin_stats")
    user_button = types.InlineKeyboardButton("👤 Информация о пользователе", callback_data="admin_user")
    add_button = types.InlineKeyboardButton("➕ Добавить попытки", callback_data="admin_add")
    broadcast_button = types.InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast")
    back_button = types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_menu")
    
    markup.add(stats_button, user_button, add_button, broadcast_button, back_button)
    
    bot.send_message(
        message.chat.id,
        "🔧 *Админ-панель*\n\n"
        "Выберите действие:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_callback(call):
    """Обработка нажатий на кнопки админ-панели"""
    user_id = call.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ У вас нет доступа к этой функции.", show_alert=True)
        return
    
    action = call.data.split('_')[1]
    
    if action == "stats":
        # Показываем общую статистику
        stats = firebase_manager.get_admin_stats()
        
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.edit_message_text(
            f"📊 *Общая статистика*\n\n"
            f"👥 Всего пользователей: {stats['total_users']}\n"
            f"🔍 Всего анализов: {stats['total_attempts_used']}\n"
            f"💰 Всего оплат: {stats['total_payments']}\n"
            f"💵 Общая сумма: {stats['total_amount']}₽",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    elif action == "user":
        # Запрашиваем ID пользователя
        msg = bot.edit_message_text(
            "👤 Введите ID пользователя:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # Регистрируем следующий шаг
        bot.register_next_step_handler(msg, process_user_id_request)
        
    elif action == "add":
        # Запрашиваем ID пользователя и количество попыток
        msg = bot.edit_message_text(
            "➕ Введите ID пользователя и количество попыток через пробел (например: 123456789 10):",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # Регистрируем следующий шаг
        bot.register_next_step_handler(msg, process_add_attempts_request)
        
    elif action == "broadcast":
        # Запрашиваем текст рассылки
        msg = bot.edit_message_text(
            "📣 Введите текст для рассылки всем пользователям:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # Регистрируем следующий шаг
        bot.register_next_step_handler(msg, process_broadcast_request)
    
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_admin")
def back_to_admin(call):
    """Возврат в админ-панель"""
    show_admin_panel(call.message)
    bot.answer_callback_query(call.id)

def process_user_id_request(message):
    """Обработка запроса информации о пользователе"""
    user_id = message.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас нет доступа к этой функции.")
        return
    
    try:
        target_user_id = int(message.text.strip())
        user_info = firebase_manager.get_user_stats(target_user_id)
        
        if not user_info:
            markup = types.InlineKeyboardMarkup()
            back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
            markup.add(back_button)
            
            bot.reply_to(
                message, 
                f"❌ Пользователь с ID {target_user_id} не найден.",
                reply_markup=markup
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        add_button = types.InlineKeyboardButton(
            "➕ Добавить попытки этому пользователю", 
            callback_data=f"admin_add_to_{target_user_id}"
        )
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(add_button, back_button)
        
        bot.reply_to(
            message,
            f"👤 *Информация о пользователе*\n\n"
            f"ID: {target_user_id}\n"
            f"Попыток: {user_info.get('attempts', 0)}\n"
            f"Всего использовано: {user_info.get('total_attempts_used', 0)}\n"
            f"Всего куплено: {user_info.get('total_purchased', 0)}\n"
            f"Создан: {user_info.get('created_at_formatted', 'Неизвестно')}\n"
            f"Последнее использование: {user_info.get('last_used_formatted', 'Никогда')}",
            parse_mode="Markdown",
            reply_markup=markup
        )
        
    except ValueError:
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            "❌ Некорректный ID пользователя. Введите числовой ID.",
            reply_markup=markup
        )

def process_add_attempts_request(message):
    """Обработка запроса на добавление попыток"""
    user_id = message.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас нет доступа к этой функции.")
        return
    
    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            raise ValueError("Неверный формат")
        
        target_user_id = int(parts[0])
        amount = int(parts[1])
        
        if amount <= 0:
            raise ValueError("Количество должно быть положительным")
        
        firebase_manager.add_attempts(target_user_id, amount)
        
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            f"✅ Пользователю {target_user_id} добавлено {amount} попыток.",
            reply_markup=markup
        )
        
    except ValueError as e:
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            f"❌ Ошибка: {str(e)}. Введите ID пользователя и количество попыток через пробел.",
            reply_markup=markup
        )

def process_broadcast_request(message):
    """Обработка запроса на рассылку"""
    user_id = message.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас нет доступа к этой функции.")
        return
    
    broadcast_text = message.text.strip()
    
    if not broadcast_text:
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            "❌ Текст рассылки не может быть пустым.",
            reply_markup=markup
        )
        return
    
    # Запрашиваем подтверждение
    markup = types.InlineKeyboardMarkup(row_width=2)
    confirm_button = types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_broadcast_{message.message_id}")
    cancel_button = types.InlineKeyboardButton("❌ Отменить", callback_data="back_to_admin")
    markup.add(confirm_button, cancel_button)
    
    bot.reply_to(
        message,
        f"📣 *Предпросмотр рассылки:*\n\n{broadcast_text}\n\n"
        f"Отправить это сообщение всем пользователям?",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_broadcast_'))
def confirm_broadcast(call):
    """Подтверждение и выполнение рассылки"""
    user_id = call.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ У вас нет доступа к этой функции.", show_alert=True)
        return
    
    # Получаем ID сообщения с текстом рассылки
    message_id = int(call.data.split('_')[2])
    
    try:
        # Получаем текст рассылки из предыдущего сообщения
        broadcast_text = bot.get_message(call.message.chat.id, message_id).text
        
        # Отправляем сообщение о начале рассылки
        status_msg = bot.edit_message_text(
            "⏳ Начинаю рассылку...",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
        # Получаем всех пользователей
        users = firebase_manager.get_all_users()
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                user_id = user.get('user_id')
                if user_id:
                    bot.send_message(user_id, broadcast_text)
                    sent_count += 1
                    
                    # Обновляем статус каждые 10 отправленных сообщений
                    if sent_count % 10 == 0:
                        bot.edit_message_text(
                            f"⏳ Отправлено: {sent_count}/{len(users)}...",
                            chat_id=status_msg.chat.id,
                            message_id=status_msg.message_id
                        )
            except Exception as e:
                logging.error(f"Error sending broadcast to {user.get('user_id')}: {str(e)}")
                failed_count += 1
        
        # Создаем кнопку возврата
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        # Обновляем сообщение с финальным статусом
        bot.edit_message_text(
            f"✅ Рассылка завершена!\n\n"
            f"✓ Успешно отправлено: {sent_count}\n"
            f"✗ Ошибок: {failed_count}\n"
            f"📊 Всего пользователей: {len(users)}",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_add_to_'))
def add_attempts_to_user(call):
    """Добавление попыток конкретному пользователю"""
    admin_id = call.from_user.id
    
    # Проверка прав администратора
    if admin_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ У вас нет доступа к этой функции.", show_alert=True)
        return
    
    # Получаем ID пользователя
    target_user_id = int(call.data.split('_')[-1])
    
    # Запрашиваем количество попыток
    msg = bot.edit_message_text(
        f"➕ Введите количество попыток для добавления пользователю {target_user_id}:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    
    # Сохраняем ID пользователя в контексте
    bot.register_next_step_handler(msg, lambda m: process_add_attempts_to_user(m, target_user_id))
    
    bot.answer_callback_query(call.id)

def process_add_attempts_to_user(message, target_user_id):
    """Обработка запроса на добавление попыток конкретному пользователю"""
    user_id = message.from_user.id
    
    # Проверка прав администратора
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ У вас нет доступа к этой функции.")
        return
    
    try:
        amount = int(message.text.strip())
        
        if amount <= 0:
            raise ValueError("Количество должно быть положительным")
        
        firebase_manager.add_attempts(target_user_id, amount)
        
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            f"✅ Пользователю {target_user_id} добавлено {amount} попыток.",
            reply_markup=markup
        )
        
    except ValueError as e:
        markup = types.InlineKeyboardMarkup()
        back_button = types.InlineKeyboardButton("◀️ Назад в админ-панель", callback_data="back_to_admin")
        markup.add(back_button)
        
        bot.reply_to(
            message, 
            f"❌ Ошибка: {str(e)}. Введите положительное число.",
            reply_markup=markup
        )

# Функция для проверки, является ли текст ссылкой на Wildberries
def is_wildberries_link(text):
    logger.debug(f"Checking if text is a Wildberries link: {text}")
    # Проверка на ссылку Wildberries
    return bool(re.search(r'https?://[^/]*wildberries\.ru/[^\s]+', text))

# Функция для проверки, является ли текст артикулом
def is_article_number(text):
    logger.debug(f"Checking if text is an article number: {text}")
    # Проверка на артикул (обычно это число)
    return bool(re.match(r'^\d+$', text.strip()))

def process_wildberries_link(message):
    try:
        # Извлекаем артикул из ссылки
        article = extract_article_from_link(message.text)
        if article:
            logger.info(f"Extracted article {article} from link")
            # Обрабатываем артикул
            process_article_number(message, article)
        else:
            logger.warning(f"Could not extract article from link: {message.text}")
            bot.reply_to(message, "Не удалось извлечь артикул из ссылки. Пожалуйста, отправьте артикул напрямую.")
    except Exception as e:
        logger.error(f"Error processing Wildberries link: {str(e)}", exc_info=True)
        bot.reply_to(message, "Произошла ошибка при обработке ссылки. Попробуйте отправить артикул напрямую.")

def process_article_number(message, article=None):
    try:
        # Используем переданный артикул или берем из сообщения
        article = article or message.text.strip()
        
        # Проверяем, есть ли у пользователя доступные попытки
        user_id = message.from_user.id
        attempts = firebase_manager.get_attempts(user_id)
        
        if attempts <= 0:
            # У пользователя нет попыток
            logger.info(f"User {user_id} has no attempts left")
            send_no_attempts_message(message)
            return
        
        # Отправляем сообщение о начале анализа
        bot.reply_to(message, "Начинаю анализ отзывов... Это может занять некоторое время.")
        
        # Здесь должен быть код для анализа отзывов
        # ...
        
    except Exception as e:
        logger.error(f"Error processing article number: {str(e)}", exc_info=True)
        bot.reply_to(message, "Произошла ошибка при обработке артикула. Попробуйте позже.")

if __name__ == '__main__':
    # Проверяем, что все обработчики зарегистрированы
    logging.info(f"Registered handlers: {bot.message_handlers}")
    
    # Явно отключаем webhook перед запуском polling
    bot.remove_webhook()
    bot.polling(none_stop=True)
