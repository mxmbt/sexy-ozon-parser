import os
import sys
from dotenv import load_dotenv
import random

# Проверяем режим запуска (debug или production)
DEBUG_MODE = '--debug' in sys.argv

# Загружаем переменные окружения из соответствующего .env файла
if DEBUG_MODE:
    # В режиме отладки используем .env.debug
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env.debug')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print(f"Загружены настройки отладки из {dotenv_path}")
else:
    # Проверяем наличие обычного .env файла для обратной совместимости
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

# Настройки парсера
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"  # По умолчанию headless=true для production
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