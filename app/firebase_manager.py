import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from config import FIREBASE_CREDENTIALS, FIREBASE_PROJECT_ID
import logging

logger = logging.getLogger(__name__)

class FirebaseManager:
    def __init__(self):
        # Инициализация Firebase с вашим service account key
        cred = credentials.Certificate(FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred, {
            'projectId': FIREBASE_PROJECT_ID
        })
        self.db = firestore.client()

    def get_user_attempts(self, user_id: int) -> int:
        """Получение количества оставшихся попыток пользователя"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('attempts', 0)
        else:
            # Создаем нового пользователя с 1 попыткой
            doc_ref.set({
                'user_id': user_id,
                'attempts': 1,
                'created_at': datetime.now(),
                'total_attempts_used': 0
            })
            return 1

    def decrease_attempts(self, user_id: int) -> int:
        """Уменьшение количества попыток"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            attempts = doc.to_dict().get('attempts', 0)
            total_used = doc.to_dict().get('total_attempts_used', 0)
            if attempts > 0:
                doc_ref.update({
                    'attempts': attempts - 1,
                    'total_attempts_used': total_used + 1,
                    'last_used': datetime.now()
                })
                return attempts - 1
        return 0

    def add_attempts(self, user_id: int, amount: int = 10):
        """Добавление попыток после оплаты"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        current_attempts = doc.to_dict().get('attempts', 0) if doc.exists else 0
        total_purchased = doc.to_dict().get('total_purchased', 0) if doc.exists else 0
        
        doc_ref.set({
            'user_id': user_id,
            'attempts': current_attempts + amount,
            'total_purchased': total_purchased + amount,
            'last_purchase': datetime.now(),
            'updated_at': datetime.now()
        }, merge=True)

    def get_user_stats(self, user_id: int) -> dict:
        """Получение статистики пользователя"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        
        if not doc.exists:
            return {
                'attempts': 0,
                'total_attempts_used': 0,
                'total_purchased': 0
            }
        
        user_data = doc.to_dict()
        
        # Форматируем даты для удобного отображения
        if 'created_at' in user_data and user_data['created_at']:
            user_data['created_at_formatted'] = user_data['created_at'].strftime('%d.%m.%Y')
        
        if 'last_used' in user_data and user_data['last_used']:
            user_data['last_used_formatted'] = user_data['last_used'].strftime('%d.%m.%Y %H:%M')
        
        return user_data

    def add_referral(self, referrer_id: int, referred_id: int):
        """Добавление реферала и начисление бонуса"""
        # Проверяем, не был ли этот пользователь уже приглашен
        ref_doc = self.db.collection('referrals').document(f"{referrer_id}_{referred_id}")
        if ref_doc.get().exists:
            return False
        
        # Записываем информацию о реферале
        ref_doc.set({
            'referrer_id': referrer_id,
            'referred_id': referred_id,
            'created_at': datetime.now()
        })
        
        # Начисляем бонус реферреру
        self.add_attempts(referrer_id, 2)
        
        return True

    def get_referral_count(self, user_id: int) -> int:
        """Получение количества рефералов пользователя"""
        refs = self.db.collection('referrals').where('referrer_id', '==', user_id).get()
        return len(refs)

    def get_inactive_users(self, days: int = 7) -> list:
        """Получение списка неактивных пользователей"""
        # Вычисляем дату, до которой считаем пользователей неактивными
        inactive_date = datetime.now() - timedelta(days=days)
        
        # Получаем пользователей, которые не использовали бота после этой даты
        # или вообще не имеют записи о последнем использовании
        users = []
        
        # Пользователи с записью о последнем использовании
        query1 = self.db.collection('users').where('last_used', '<', inactive_date).get()
        for doc in query1:
            users.append(doc.to_dict())
        
        # Пользователи без записи о последнем использовании, но с созданием аккаунта раньше inactive_date
        query2 = self.db.collection('users').where('created_at', '<', inactive_date).get()
        for doc in query2:
            if 'last_used' not in doc.to_dict():
                users.append(doc.to_dict())
        
        return users

    def get_admin_stats(self) -> dict:
        """Получение общей статистики для администраторов"""
        stats = {
            'total_users': 0,
            'total_attempts_used': 0,
            'total_payments': 0,
            'total_amount': 0
        }
        
        # Подсчет пользователей
        users = self.db.collection('users').get()
        stats['total_users'] = len(users)
        
        # Подсчет использованных попыток и платежей
        for user_doc in users:
            user_data = user_doc.to_dict()
            stats['total_attempts_used'] += user_data.get('total_attempts_used', 0)
            stats['total_payments'] += 1 if user_data.get('total_purchased', 0) > 0 else 0
        
        # Подсчет общей суммы платежей (если есть коллекция payments)
        payments = self.db.collection('payments').get()
        for payment in payments:
            payment_data = payment.to_dict()
            stats['total_amount'] += payment_data.get('amount', 0)
        
        return stats

    def save_feedback(self, user_id: int, feedback_text: str):
        """Сохранение отзыва пользователя"""
        self.db.collection('feedback').add({
            'user_id': user_id,
            'text': feedback_text,
            'created_at': datetime.now()
        })

    def set_user_language(self, user_id: int, language: str):
        """Установка языка пользователя"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc_ref.set({
            'language': language,
            'updated_at': datetime.now()
        }, merge=True)

    def get_user_language(self, user_id: int) -> str:
        """Получение языка пользователя"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('language', 'ru')
        return 'ru'

    def get_last_analysis(self, user_id: int) -> dict:
        """Получение последнего анализа пользователя"""
        analyses = self.db.collection('analyses').where('user_id', '==', user_id).order_by('created_at', direction='DESCENDING').limit(1).get()
        
        for analysis in analyses:
            data = analysis.to_dict()
            if 'created_at' in data:
                data['created_at_formatted'] = data['created_at'].strftime('%d.%m.%Y %H:%M')
            return data
        
        return None

    def save_analysis(self, user_id: int, sku: str, item_name: str, analysis_text: str):
        """Сохранение результатов анализа"""
        self.db.collection('analyses').add({
            'user_id': user_id,
            'sku': sku,
            'item_name': item_name,
            'analysis_text': analysis_text,
            'created_at': datetime.now()
        })

    def set_comparison_product(self, user_id: int, position: int, product_link: str):
        """Сохранение товара для сравнения"""
        doc_ref = self.db.collection('users').document(str(user_id))
        
        if position == 1:
            doc_ref.set({
                'comparison': {
                    'product1': product_link,
                    'updated_at': datetime.now()
                }
            }, merge=True)
        else:
            doc_ref.set({
                'comparison': {
                    'product2': product_link,
                    'updated_at': datetime.now()
                }
            }, merge=True)

    def get_comparison_product(self, user_id: int, position: int) -> str:
        """Получение товара для сравнения"""
        doc_ref = self.db.collection('users').document(str(user_id))
        doc = doc_ref.get()
        
        if doc.exists and 'comparison' in doc.to_dict():
            comparison = doc.to_dict()['comparison']
            if position == 1 and 'product1' in comparison:
                return comparison['product1']
            elif position == 2 and 'product2' in comparison:
                return comparison['product2']
        
        return None

    def get_all_users(self) -> list:
        """Получение списка всех пользователей"""
        users = []
        docs = self.db.collection('users').get()
        
        for doc in docs:
            user_data = doc.to_dict()
            if 'user_id' in user_data:
                users.append(user_data)
        
        return users

    def record_payment(self, user_id: int, amount: float, plan: str):
        """Запись информации о платеже"""
        self.db.collection('payments').add({
            'user_id': user_id,
            'amount': amount,
            'plan': plan,
            'created_at': datetime.now()
        })

    def get_attempts(self, user_id):
        try:
            doc_ref = self.db.collection('users').document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                user_data = doc.to_dict()
                return user_data.get('attempts', 0)
            else:
                # Создаем документ для нового пользователя
                doc_ref.set({'attempts': 0, 'created_at': firestore.SERVER_TIMESTAMP})
                return 0
        except Exception as e:
            logger.error(f"Error getting attempts for user {user_id}: {str(e)}")
            return 0 