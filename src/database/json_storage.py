import os
import json
from datetime import datetime
from src.utils.logger import log_info, log_error
from src.utils.config import REVIEW_STORAGE_PATH

class ReviewsStorage:
    """
    Класс для хранения отзывов в JSON-файлах.
    Каждый продукт сохраняется в отдельный файл.
    """
    
    def __init__(self):
        """Инициализирует хранилище отзывов"""
        self.storage_dir = REVIEW_STORAGE_PATH
        
        # Создаем каталог для хранения отзывов, если он не существует
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
            log_info(f"Создан каталог для хранения отзывов: {self.storage_dir}")
            
        # Создаем файл для хранения метаданных, если он не существует
        self.metadata_file = os.path.join(self.storage_dir, "metadata.json")
        if not os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'w', encoding='utf-8') as file:
                json.dump({}, file, ensure_ascii=False, indent=2)
            log_info(f"Создан файл метаданных: {self.metadata_file}")

    def _get_filename(self, product_id):
        """Генерирует имя файла для хранения отзывов о продукте"""
        return os.path.join(self.storage_dir, f"reviews_{product_id}.json")
    
    def _load_reviews(self, product_id):
        """Загружает существующие отзывы из файла"""
        filename = self._get_filename(product_id)
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as file:
                    return json.load(file)
            except json.JSONDecodeError:
                log_error(f"Ошибка чтения JSON из файла {filename}. Создаем новый файл.")
                return []
        return []
    
    def _load_metadata(self):
        """Загружает метаданные продуктов"""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as file:
                    return json.load(file)
            except json.JSONDecodeError:
                log_error(f"Ошибка чтения JSON из файла метаданных. Создаем новый файл.")
                return {}
        return {}
    
    def _save_metadata(self, metadata):
        """Сохраняет метаданные продуктов"""
        with open(self.metadata_file, 'w', encoding='utf-8') as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2)
    
    def update_product_metadata(self, product_id, last_review_date=None, last_review_ids=None, total_reviews=None):
        """
        Обновляет метаданные о продукте
        
        Args:
            product_id (str): ID продукта
            last_review_date (str, optional): Дата последнего собранного отзыва
            last_review_ids (list, optional): Список ID последних отзывов (до 20 штук)
            total_reviews (int, optional): Общее количество отзывов
        """
        metadata = self._load_metadata()
        
        # Обновляем или создаем запись для продукта
        if product_id not in metadata:
            metadata[product_id] = {}
            
        product_data = metadata[product_id]
        
        # Обновляем данные, если они предоставлены
        if last_review_date:
            product_data['last_review_date'] = last_review_date
        
        # Сохраняем до 20 последних ID отзывов
        if last_review_ids:
            if not isinstance(last_review_ids, list):
                last_review_ids = [last_review_ids]
                
            if 'last_review_ids' not in product_data:
                product_data['last_review_ids'] = []
                
            # Объединяем новые ID с существующими, избегая дубликатов
            existing_ids = set(product_data['last_review_ids'])
            for review_id in last_review_ids:
                if review_id and review_id not in existing_ids:
                    existing_ids.add(review_id)
                    
            # Оставляем только 20 последних ID
            product_data['last_review_ids'] = list(existing_ids)[-20:]
            
        if total_reviews is not None:
            product_data['total_reviews'] = total_reviews
            
        # Обновляем дату последнего парсинга
        product_data['last_parsed'] = datetime.now().isoformat()
        
        # Сохраняем обновленные метаданные
        self._save_metadata(metadata)
        log_info(f"Обновлены метаданные для продукта {product_id}")

    def get_last_review_date(self, product_id):
        """Получает дату последнего собранного отзыва для продукта"""
        metadata = self._load_metadata()
        
        if product_id in metadata and 'last_review_date' in metadata[product_id]:
            return metadata[product_id]['last_review_date']
            
        return None
    
    def get_last_review_ids(self, product_id):
        """
        Получает список ID последних собранных отзывов для продукта
        
        Args:
            product_id (str): ID продукта
            
        Returns:
            list: Список ID последних отзывов (до 20 штук)
        """
        metadata = self._load_metadata()
        
        if product_id in metadata and 'last_review_ids' in metadata[product_id]:
            return metadata[product_id]['last_review_ids']
            
        return []
    
    def save_review(self, review):
        """Сохраняет отзыв в файл"""
        if not review or 'product_id' not in review:
            log_error("Ошибка: отзыв не содержит идентификатор продукта")
            return False
        
        product_id = review['product_id']
        
        # Загружаем существующие отзывы
        reviews = self._load_reviews(product_id)
        
        # Проверяем, есть ли уже отзыв с таким ID
        review_exists = any(r.get('review_id') == review.get('review_id') for r in reviews)
        
        if not review_exists:
            # Добавляем временную метку сохранения
            review['saved_at'] = datetime.now().isoformat()
            reviews.append(review)
            
            # Сохраняем обновленный список отзывов
            filename = self._get_filename(product_id)
            with open(filename, 'w', encoding='utf-8') as file:
                json.dump(reviews, file, ensure_ascii=False, indent=2)
                
            # Обновляем метаданные для инкрементного парсинга
            if 'date' in review and 'review_id' in review:
                self.update_product_metadata(
                    product_id, 
                    last_review_date=review['date'],
                    last_review_ids=review['review_id'],
                    total_reviews=len(reviews)
                )
                
            return True
        
        return False  # Отзыв уже существует
    
    def save_reviews(self, reviews):
        """Сохраняет несколько отзывов"""
        if not reviews:
            return 0
        
        saved_count = 0
        for review in reviews:
            if self.save_review(review):
                saved_count += 1
        
        return saved_count
    
    def get_product_reviews(self, product_id=None, product_url=None, limit=100):
        """Получает отзывы о продукте по ID или URL"""
        if not product_id and not product_url:
            log_error("Ошибка: необходимо указать product_id или product_url")
            return []
        
        # Если указан URL, но не указан ID, извлекаем ID из URL
        if not product_id and product_url:
            # Простое извлечение ID из URL (может потребоваться настройка)
            parts = product_url.split('/')
            for part in parts:
                if part.isdigit():
                    product_id = part
                    break
        
        if not product_id:
            log_error("Не удалось определить ID продукта")
            return []
        
        reviews = self._load_reviews(product_id)
        
        # Ограничиваем количество возвращаемых отзывов
        return reviews[:limit] if limit else reviews
    
    def close(self):
        """Закрывает соединение с хранилищем данных"""
        # Для JSON-файлов ничего не нужно закрывать
        pass 