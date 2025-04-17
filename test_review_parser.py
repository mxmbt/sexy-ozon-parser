#!/usr/bin/env python
import os
import time
import logging
import json
import argparse
from dotenv import load_dotenv
from parsers.lube_ozon_review_parser import OzonReviewParser
from src.utils.logger import log_info, log_error, log_warning, log_debug
from src.utils.config import (
    HEADLESS, USER_AGENT, REQUEST_TIMEOUT, DEFAULT_DELAY,
    MAX_REVIEWS_PER_PRODUCT, INCREMENTAL_PARSING
)
from playwright.sync_api import sync_playwright

# Загрузка переменных окружения
load_dotenv()

# Настройка уровня логирования
os.environ['LOG_LEVEL'] = 'DEBUG'
logging.getLogger().setLevel(logging.DEBUG)


def test_review_parsing(test_url=None, max_reviews=None, incremental=None, debug_mode=True):
    """
    Тестирование парсера отзывов с подробным логированием и проверкой пагинации
    
    Args:
        test_url (str, optional): URL товара для тестирования. Если не указан, используется значение по умолчанию.
        max_reviews (int, optional): Максимальное количество отзывов для сбора.
        incremental (bool, optional): Использовать ли инкрементный режим парсинга.
        debug_mode (bool, optional): Включить ли режим отладки с сохранением скриншотов.
    """
    # URL товара для тестирования - короткая версия как рекомендовано
    if not test_url:
        test_url = "https://www.ozon.ru/product/prezervativy-unilatex-ultrathin-12-sht-3-sht-v-podarok-210502516/"
    
    log_info("Запуск тестирования парсера отзывов")
    log_info(f"Тестовый URL: {test_url}")
    
    # Инициализация парсера с режимом отладки
    parser = OzonReviewParser(debug_mode=debug_mode)
    
    try:
        # Установка параметров для отладки
        os.environ['HEADLESS'] = 'false' if debug_mode else 'true'
        os.environ['LOG_LEVEL'] = 'DEBUG' if debug_mode else 'INFO'
        
        log_info("Запуск браузера...")
        # Запуск браузера и настройка
        parser._initialize_browser()
        
        # Вывод используемых настроек
        log_info(f"Используемый User-Agent: {USER_AGENT}")
        log_info(f"Таймаут запросов: {REQUEST_TIMEOUT} сек.")
        log_info(f"Задержка между запросами: {DEFAULT_DELAY} сек.")
        log_info(f"Режим отладки: {'включен' if debug_mode else 'выключен'}")
        log_info(f"Инкрементный режим: {'включен' if incremental else 'выключен (полный парсинг)'}")
        log_info(f"Максимальное количество отзывов: {max_reviews if max_reviews else MAX_REVIEWS_PER_PRODUCT}")
        
        # Запуск парсинга через основной метод 
        all_reviews = parser.parse_product_reviews(
            product_url=test_url,
            max_reviews=max_reviews,
            incremental=incremental
        )
        
        # Сохранение всех собранных отзывов
        if all_reviews:
            log_info(f"Всего собрано {len(all_reviews)} отзывов")
            with open("test_reviews.json", "w", encoding="utf-8") as f:
                json.dump(all_reviews, f, ensure_ascii=False, indent=2)
            log_info("Все отзывы сохранены в файл test_reviews.json")
        else:
            log_error("Не удалось собрать ни одного отзыва!")
        
    except Exception as e:
        log_error(f"Критическая ошибка при тестировании: {e}", exc_info=True)
    finally:
        # Закрытие браузера
        log_info("Закрытие браузера...")
        parser.close()
        log_info("Тестирование завершено")


def test_screenshot():
    """Делает скриншот страницы с отзывами для анализа структуры"""
    url = "https://www.ozon.ru/product/prezervativy-unilatex-ultrathin-12-sht-3-sht-v-podarok-210502516/"
    reviews_url = f"{url}reviews/"
    
    print(f"Тестирование URL: {reviews_url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Запускаем в видимом режиме
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        
        # Открываем страницу
        print("Открываем страницу отзывов...")
        page.goto(reviews_url, wait_until="domcontentloaded")
        time.sleep(5)  # Ждем загрузки
        
        # Делаем скриншот
        screenshot_path = "reviews_page_screenshot.png"
        page.screenshot(path=screenshot_path)
        print(f"Скриншот сохранен: {screenshot_path}")
        
        # Получаем HTML структуру страницы
        html_content = page.content()
        with open("reviews_page_html.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("HTML страницы сохранен в reviews_page_html.html")
        
        # Ищем элементы отзывов
        review_elements = page.query_selector_all('div[data-review-uuid]')
        print(f"Найдено элементов с data-review-uuid: {len(review_elements)}")
        
        # Пробуем другие селекторы
        other_selectors = [
            'div.review-item', 
            'div[itemprop="review"]',
            'div[data-widget="webReviewsList"]',
            'div:has-text("отзыв")'
        ]
        
        for selector in other_selectors:
            elements = page.query_selector_all(selector)
            print(f"Селектор {selector}: найдено {len(elements)} элементов")
        
        # Смотрим элементы с текстом "отзыв"
        review_text_elements = page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll('*'))
                .filter(el => el.innerText && el.innerText.toLowerCase().includes('отзыв'));
            return elements.length;
        }""")
        print(f"Элементов с текстом 'отзыв': {review_text_elements}")
        
        # Проверяем содержимое страницы на наличие "У этого товара пока нет отзывов"
        if page.get_by_text("У этого товара пока нет отзывов").is_visible():
            print("На странице указано: У этого товара пока нет отзывов")
        
        # Ждем чтобы увидеть страницу
        time.sleep(10)
        
        browser.close()


if __name__ == "__main__":
    # Парсинг аргументов командной строки для гибкого тестирования
    parser = argparse.ArgumentParser(description='Тестирование парсера отзывов Ozon')
    parser.add_argument('--url', type=str, help='URL товара для тестирования')
    parser.add_argument('--max-reviews', type=int, help='Максимальное количество отзывов для сбора')
    parser.add_argument('--incremental', action='store_true', help='Использовать инкрементный режим парсинга')
    parser.add_argument('--full', action='store_true', help='Использовать полный режим парсинга')
    parser.add_argument('--debug', action='store_true', help='Включить режим отладки с сохранением скриншотов')
    parser.add_argument('--no-debug', action='store_true', help='Выключить режим отладки')
    
    args = parser.parse_args()
    
    # Определение параметров
    test_url = args.url
    max_reviews = args.max_reviews
    
    # Определение режима инкрементного парсинга
    incremental = None
    if args.incremental:
        incremental = True
    elif args.full:
        incremental = False
    
    # Определение режима отладки
    debug_mode = True
    if args.debug:
        debug_mode = True
    elif args.no_debug:
        debug_mode = False
    
    # Запуск тестирования
    test_review_parsing(test_url, max_reviews, incremental, debug_mode)
    test_screenshot() 