import os
from dotenv import load_dotenv
import random

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройки парсера
HEADLESS = os.getenv("HEADLESS", "false").lower() == "true"
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30000"))
DEFAULT_DELAY = int(os.getenv("DEFAULT_DELAY", "300"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

# Лимиты и интервалы
MAX_REVIEWS_PER_PRODUCT = int(os.getenv("MAX_REVIEWS_PER_PRODUCT", "5000"))
MIN_DELAY = int(os.getenv("MIN_DELAY_BETWEEN_REQUESTS", "2000"))
MAX_DELAY = int(os.getenv("MAX_DELAY_BETWEEN_REQUESTS", "5000"))

# Настройки инкрементного парсинга
INCREMENTAL_PARSING = os.getenv("INCREMENTAL_PARSING", "true").lower() == "true"
REVIEW_STORAGE_PATH = os.getenv("REVIEW_STORAGE_PATH", "data/reviews")

def get_random_delay():
    """Возвращает случайную задержку между MIN_DELAY и MAX_DELAY"""
    return random.randint(MIN_DELAY, MAX_DELAY) / 1000.0 