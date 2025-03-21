import pymongo
from datetime import datetime
from pymongo.errors import PyMongoError
from src.utils.config import MONGO_URI, MONGO_DB, MONGO_COLLECTION
from src.utils.logger import log_info, log_error

class ReviewsDatabase:
    def __init__(self):
        """Инициализация подключения к базе данных MongoDB"""
        try:
            self.client = pymongo.MongoClient(MONGO_URI)
            self.db = self.client[MONGO_DB]
            self.collection = self.db[MONGO_COLLECTION]
            
            # Создаем индексы для оптимизации запросов
            self.collection.create_index([("product_id", pymongo.ASCENDING)])
            self.collection.create_index([("product_url", pymongo.ASCENDING)])
            self.collection.create_index([("review_id", pymongo.ASCENDING)], unique=True)
            
            log_info(f"Подключение к MongoDB успешно установлено: {MONGO_URI}")
        except PyMongoError as e:
            log_error(f"Ошибка подключения к MongoDB: {e}", exc_info=True)
            raise

    def save_review(self, review_data):
        """
        Сохранение отзыва в базу данных
        
        Args:
            review_data (dict): Данные отзыва
        
        Returns:
            bool: True, если сохранение успешно, иначе False
        """
        try:
            # Добавляем метку времени
            review_data["parsed_at"] = datetime.now()
            
            # Используем upsert для обновления существующей записи или вставки новой
            result = self.collection.update_one(
                {"review_id": review_data["review_id"]},
                {"$set": review_data},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count > 0:
                log_info(f"Отзыв {review_data['review_id']} успешно сохранен")
                return True
            else:
                log_info(f"Отзыв {review_data['review_id']} уже существует и не изменился")
                return True
        except PyMongoError as e:
            log_error(f"Ошибка при сохранении отзыва: {e}", exc_info=True)
            return False

    def save_reviews(self, reviews):
        """
        Сохранение списка отзывов в базу данных
        
        Args:
            reviews (list): Список отзывов
        
        Returns:
            int: Количество успешно сохраненных отзывов
        """
        success_count = 0
        
        for review in reviews:
            if self.save_review(review):
                success_count += 1
                
        return success_count
    
    def get_product_reviews(self, product_id=None, product_url=None, limit=100):
        """
        Получение отзывов о продукте
        
        Args:
            product_id (str, optional): ID продукта
            product_url (str, optional): URL продукта
            limit (int, optional): Максимальное количество отзывов
            
        Returns:
            list: Список отзывов
        """
        query = {}
        
        if product_id:
            query["product_id"] = product_id
        elif product_url:
            query["product_url"] = product_url
        
        try:
            return list(self.collection.find(query).limit(limit))
        except PyMongoError as e:
            log_error(f"Ошибка при получении отзывов: {e}", exc_info=True)
            return []
    
    def close(self):
        """Закрытие соединения с базой данных"""
        try:
            self.client.close()
            log_info("Соединение с MongoDB закрыто")
        except PyMongoError as e:
            log_error(f"Ошибка при закрытии соединения с MongoDB: {e}", exc_info=True) 