from urllib.parse import urlencode
from config import WEBHOOK_HOST  # Вернем импорт WEBHOOK_HOST
import logging

class PaymentManager:
    def __init__(self):
        self.wallet = "4100117527556990"  # Номер кошелька ЮMoney
        self.plans = {
            'basic': {'amount': 50, 'attempts': 10, 'name': 'Базовый'},
            'standard': {'amount': 150, 'attempts': 30, 'name': 'Стандарт'},
            'premium': {'amount': 350, 'attempts': 70, 'name': 'Премиум'}
        }
        self.amount = self.plans['basic']['amount']  # По умолчанию базовый план

    def create_payment_link(self, user_id: int, plan: str = 'basic') -> str:
        """Создание ссылки на оплату"""
        if plan not in self.plans:
            plan = 'basic'
        
        plan_data = self.plans[plan]
        
        payment_params = {
            'targets': f'Анализ отзывов WB - {plan_data["name"]}',
            'default-sum': plan_data['amount'],
            'button-text': 'pay',
            'any-card-payment-type': 'on',
            'button-size': 'm',
            'button-color': 'orange',
            'mail': 'on',
            'successURL': f'{WEBHOOK_HOST}/webhook/payment-success?userId={user_id}',
            'quickpay-form': 'shop',
            'account': self.wallet,
            'label': f'wb_review_bot_{user_id}_{plan}',
            'need-fio': 'false',
            'need-email': 'false',
            'need-phone': 'false',
            'redirect': 'true',
            'clearCache': 'true',
            'autoReturn': 'true',
            'targets-hint': '',
            'return-url': f'{WEBHOOK_HOST}/webhook/payment-success?userId={user_id}'
        }
        
        return f"https://yoomoney.ru/quickpay/button-widget?{urlencode(payment_params)}"

    def get_payment_message(self) -> tuple[str, list]:
        """Возвращает сообщение с инструкцией и данные для кнопок"""
        message = (
            "❌ У вас закончились попытки анализа!\n\n"
            "Выберите подходящий тарифный план:\n"
            f"🔹 *Базовый*: {self.plans['basic']['attempts']} попыток за {self.plans['basic']['amount']}₽\n"
            f"🔹 *Стандарт*: {self.plans['standard']['attempts']} попыток за {self.plans['standard']['amount']}₽ (экономия 25%)\n"
            f"🔹 *Премиум*: {self.plans['premium']['attempts']} попыток за {self.plans['premium']['amount']}₽ (экономия 40%)\n\n"
            "После оплаты попытки будут начислены автоматически"
        )
        
        buttons = [
            {'text': f"💳 Базовый ({self.plans['basic']['amount']}₽)", 'plan': 'basic'},
            {'text': f"💳 Стандарт ({self.plans['standard']['amount']}₽)", 'plan': 'standard'},
            {'text': f"💳 Премиум ({self.plans['premium']['amount']}₽)", 'plan': 'premium'}
        ]
        
        return message, buttons

    def verify_payment(self, notification_data: dict) -> tuple[bool, int]:
        """Проверка уведомления об оплате"""
        try:
            # Проверяем сумму
            amount = float(notification_data.get('amount', 0))
            if amount != self.amount:
                logging.warning(f"Payment amount mismatch: expected {self.amount}, got {amount}")
                return False, 0

            # Проверяем статус платежа
            status = notification_data.get('status', '')
            if status != 'success':
                logging.warning(f"Payment status is not success: {status}")
                return False, 0

            # Получаем ID пользователя из label
            label = notification_data.get('label', '')
            if not label.startswith('wb_review_bot_'):
                logging.warning(f"Invalid payment label: {label}")
                return False, 0

            user_id = int(label.split('_')[-1])
            logging.info(f"Payment verified for user {user_id}")
            return True, user_id

        except Exception as e:
            logging.error(f"Payment verification error: {str(e)}")
            return False, 0 