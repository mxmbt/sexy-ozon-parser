import logging
import os
from datetime import datetime

# Создаем директорию для логов, если она не существует
os.makedirs("logs", exist_ok=True)

# Настраиваем форматирование логов
log_format = "%(asctime)s - %(levelname)s - %(message)s"
date_format = "%Y-%m-%d %H:%M:%S"

# Настраиваем логгер
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=date_format,
    handlers=[
        logging.FileHandler(f"logs/parser_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("ozon_parser")

def log_info(message):
    """Логирование информационного сообщения"""
    logger.info(message)

def log_error(message, exc_info=None):
    """Логирование ошибки"""
    if exc_info:
        logger.error(message, exc_info=exc_info)
    else:
        logger.error(message)

def log_warning(message):
    """Логирование предупреждения"""
    logger.warning(message)

def log_debug(message):
    """Логирование отладочного сообщения"""
    logger.debug(message) 