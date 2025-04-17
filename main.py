#!/usr/bin/env python3
import argparse
import json
import os
import time
from parsers.lube_ozon_review_parser import OzonReviewParser
from src.utils.logger import log_info, log_error

def parse_args():
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(description="Парсер отзывов с Озона")
    
    parser.add_argument(
        "--url", "-u",
        type=str,
        help="URL товара для парсинга отзывов"
    )
    
    parser.add_argument(
        "--file", "-f",
        type=str,
        help="Путь к файлу со списком URL товаров (по одному URL на строку)"
    )
    
    return parser.parse_args()

def read_urls_from_file(file_path):
    """Чтение URL из файла"""
    if not os.path.exists(file_path):
        log_error(f"Файл не найден: {file_path}")
        return []
    
    with open(file_path, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    return urls

def main():
    """Основная функция парсера"""
    args = parse_args()
    
    if not args.url and not args.file:
        log_error("Необходимо указать URL товара (--url) или файл со списком URL (--file)")
        return 1
    
    # Получаем список URL для парсинга
    urls = []
    
    if args.url:
        urls.append(args.url)
    
    if args.file:
        file_urls = read_urls_from_file(args.file)
        urls.extend(file_urls)
    
    if not urls:
        log_error("Не указано ни одного URL для парсинга")
        return 1
    
    log_info(f"Начинаем парсинг отзывов для {len(urls)} товаров")
    start_time = time.time()
    
    # Создаем парсер и запускаем парсинг
    parser = OzonReviewParser()
    try:
        results = parser.parse_multiple_products(urls)
        
        # Выводим статистику
        total_reviews = sum(results.values())
        log_info(f"Парсинг завершен. Собрано {total_reviews} отзывов")
        
        for url, count in results.items():
            log_info(f"URL: {url} - собрано отзывов: {count}")
        
        # Сохраняем результаты в JSON-файл
        result_file = f"results/parsed_reviews_{int(time.time())}.json"
        os.makedirs("results", exist_ok=True)
        
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        log_info(f"Результаты сохранены в файле: {result_file}")
    except Exception as e:
        log_error(f"Ошибка при выполнении парсинга: {e}", exc_info=True)
        return 1
    finally:
        parser.close()
    
    elapsed_time = time.time() - start_time
    log_info(f"Общее время выполнения: {elapsed_time:.2f} секунд")
    
    return 0

if __name__ == "__main__":
    exit(main()) 