#!/usr/bin/env python3
"""
Скрипт для запуска парсера по расписанию.

На Unix/Linux/Mac можно запускать через cron:
# Пример для запуска каждый день в 3 часа ночи:
# 0 3 * * * /path/to/python3 /path/to/scheduled_parser.py

На Windows можно использовать Планировщик задач:
1. Откройте Планировщик задач Windows
2. Создайте новую задачу
3. В поле "Действие" укажите путь к python.exe и аргументом путь к этому файлу
4. Настройте расписание (например, ежедневно в 3:00)

Для автоматического запуска без включенного компьютера рекомендуется:
- Использовать облачный сервер (VPS, AWS, DigitalOcean и др.)
- Или настроить автоматическое включение компьютера перед запуском задачи
  (Wake-on-LAN на большинстве материнских плат, BIOS/UEFI настройки)
"""

import os
import sys
import time
import argparse
from datetime import datetime
from src.parsers.ozon_review_parser import OzonReviewParser
from src.utils.logger import log_info, log_error, log_warning
from src.utils.config import INCREMENTAL_PARSING, MAX_REVIEWS_PER_PRODUCT

# Путь к файлу со списком URL для парсинга
URL_FILE = "product_urls.txt"

def ensure_file_exists():
    """Проверяет существование файла со списком URL. Если файла нет, создает пустой файл."""
    if not os.path.exists(URL_FILE):
        with open(URL_FILE, "w", encoding="utf-8") as f:
            f.write("# Список URL товаров для парсинга отзывов (по одному URL на строку)\n")
            f.write("# Формат: URL [максимальное_количество_отзывов] [режим:full/incremental]\n")
            f.write("# Например:\n")
            f.write("# https://www.ozon.ru/product/smartfon-apple-iphone-13-128gb-belyy-608191880/ 500 incremental\n")
            f.write("# https://www.ozon.ru/product/smartfon-samsung-galaxy-s21-128gb-chernyy-123456789/ 1000 full\n")
        log_info(f"Создан пустой файл {URL_FILE}. Пожалуйста, добавьте в него URL товаров для парсинга.")
        sys.exit(1)

def read_urls():
    """
    Чтение URL из файла с опциональными параметрами.
    
    Возвращает:
        list: Список кортежей (url, max_reviews, incremental)
    """
    parsed_data = []
    with open(URL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
                
            parts = line.split()
            url = parts[0]
            
            # Парсинг дополнительных параметров, если они указаны
            max_reviews = None
            incremental = None
            
            if len(parts) >= 2:
                try:
                    max_reviews = int(parts[1])
                except ValueError:
                    # Если второй параметр не число, проверяем, может это режим
                    if parts[1].lower() in ["incremental", "full"]:
                        incremental = parts[1].lower() == "incremental"
            
            if len(parts) >= 3:
                if parts[2].lower() in ["incremental", "full"]:
                    incremental = parts[2].lower() == "incremental"
            
            parsed_data.append((url, max_reviews, incremental))
            
    return parsed_data

def main(debug_mode=False, force_full=False):
    """
    Основная функция для запуска парсера по расписанию.
    
    Args:
        debug_mode (bool): Включить режим отладки с сохранением скриншотов
        force_full (bool): Принудительно запустить полный парсинг, игнорируя настройки инкрементного режима
    """
    log_info(f"Запуск планового парсинга отзывов: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_info(f"Режим отладки: {'включен' if debug_mode else 'выключен'}")
    log_info(f"Режим парсинга: {'полный (принудительно)' if force_full else 'в соответствии с настройками'}")
    
    # Проверяем наличие файла с URL
    ensure_file_exists()
    
    # Читаем URL из файла
    parsed_data = read_urls()
    
    if not parsed_data:
        log_error(f"В файле {URL_FILE} не найдено ни одного URL для парсинга.")
        return 1
    
    log_info(f"Начинаем парсинг отзывов для {len(parsed_data)} товаров")
    start_time = time.time()
    
    # Создаем парсер и запускаем парсинг
    parser = OzonReviewParser(debug_mode=debug_mode)
    
    all_results = {}
    try:
        # Обрабатываем каждый URL отдельно с его настройками
        for url, max_reviews, incremental in parsed_data:
            # Если включен принудительный полный режим, игнорируем настройки инкрементного режима
            if force_full:
                incremental = False
                
            # Используем глобальные настройки, если параметр не указан явно
            if incremental is None:
                incremental = INCREMENTAL_PARSING
                
            if max_reviews is None:
                max_reviews = MAX_REVIEWS_PER_PRODUCT
                
            log_info(f"Парсинг URL: {url}")
            log_info(f"  Режим: {'инкрементный' if incremental else 'полный'}")
            log_info(f"  Максимальное количество отзывов: {max_reviews}")
            
            try:
                reviews = parser.parse_product_reviews(url, max_reviews, incremental)
                all_results[url] = len(reviews)
                log_info(f"  Собрано отзывов: {len(reviews)}")
            except Exception as e:
                log_error(f"  Ошибка при парсинге URL {url}: {e}")
                all_results[url] = 0
                
            # Небольшая пауза между запросами к разным товарам
            time.sleep(5)
        
        # Выводим общую статистику
        total_reviews = sum(all_results.values())
        log_info(f"Парсинг завершен. Всего собрано {total_reviews} отзывов со всех товаров")
        
    except Exception as e:
        log_error(f"Критическая ошибка при выполнении планового парсинга: {e}", exc_info=True)
        return 1
    finally:
        parser.close()
    
    elapsed_time = time.time() - start_time
    log_info(f"Общее время выполнения: {elapsed_time:.2f} секунд")
    
    return 0

if __name__ == "__main__":
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description='Запуск планового парсинга отзывов Ozon')
    parser.add_argument('--debug', action='store_true', help='Включить режим отладки с сохранением скриншотов')
    parser.add_argument('--full', action='store_true', help='Принудительно запустить полный парсинг')
    
    args = parser.parse_args()
    
    sys.exit(main(debug_mode=args.debug, force_full=args.full)) 