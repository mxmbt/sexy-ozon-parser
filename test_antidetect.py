#!/usr/bin/env python3
"""
Тестовый скрипт для проверки возможности обхода защиты от ботов на сайте Ozon.
"""

import time
import random
from playwright.sync_api import sync_playwright
from src.utils.logger import log_info, log_error, log_warning

# URL для тестирования
TEST_URL = "https://www.ozon.ru/product/prezervativy-unilatex-ultrathin-12-sht-3-sht-v-podarok-210502516/?at=oZt6m0QvBhmjVk9ohkOlgQJC8NxOZVsDEGXjRi90w9pW&"

def run_test():
    """Запускает тест обхода защиты от ботов"""
    log_info("Запуск теста обхода защиты от ботов")
    
    with sync_playwright() as playwright:
        try:
            # Запускаем браузер с расширенными настройками
            browser = playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=BlockInsecurePrivateNetworkRequests'
                ]
            )
            
            # Настраиваем контекст с реалистичными параметрами
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=1.5,
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                color_scheme="light",
                reduced_motion="no-preference",
                java_script_enabled=True,
                has_touch=False,
                is_mobile=False,
                permissions=["geolocation", "notifications"],
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Pragma": "no-cache",
                    "Cache-Control": "no-cache"
                }
            )
            
            # Добавляем скрипты для обхода обнаружения автоматизации
            page = context.new_page()
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });
                
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            name: "Chrome PDF Plugin",
                            length: 1
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai",
                            name: "Chrome PDF Viewer",
                            length: 1
                        },
                        {
                            0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                            1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                            description: "Native Client",
                            filename: "internal-nacl-plugin",
                            name: "Native Client",
                            length: 2
                        }
                    ]
                });
                
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({state: Notification.permission}) :
                        originalQuery(parameters)
                );
            """)
            
            # Переходим на тестовую страницу
            log_info(f"Переход на страницу: {TEST_URL}")
            page.goto(TEST_URL, wait_until="domcontentloaded")
            
            # Добавляем случайную задержку
            time.sleep(random.uniform(3.0, 5.0))
            
            # Проверяем, есть ли ограничение доступа
            if page.get_by_text("Доступ ограничен").is_visible():
                log_warning("Обнаружено ограничение доступа, пытаемся его обойти")
                
                # Делаем скриншот страницы с ограничением
                page.screenshot(path="access_restricted.png")
                log_info("Сделан скриншот страницы с ограничением (access_restricted.png)")
                
                # Нажимаем кнопку "Обновить"
                refresh_button = page.get_by_role("button", name="Обновить")
                if refresh_button.is_visible():
                    log_info("Нажимаем кнопку 'Обновить'")
                    refresh_button.click()
                    
                    # Ждем загрузки страницы
                    page.wait_for_load_state("networkidle")
                    time.sleep(random.uniform(3.0, 5.0))
                    
                    # Проверяем, решилась ли проблема
                    if not page.get_by_text("Доступ ограничен").is_visible():
                        log_info("Удалось преодолеть ограничение доступа!")
                        page.screenshot(path="access_granted.png")
                        log_info("Сделан скриншот после преодоления ограничения (access_granted.png)")
                    else:
                        log_error("Не удалось преодолеть ограничение доступа")
                        page.screenshot(path="access_still_restricted.png")
                        log_info("Сделан скриншот страницы с сохраняющимся ограничением (access_still_restricted.png)")
            else:
                log_info("Доступ к странице получен успешно!")
                page.screenshot(path="access_success.png")
                log_info("Сделан скриншот успешного доступа (access_success.png)")
            
            # Имитируем движения мыши
            log_info("Имитация движений мыши...")
            viewport_size = page.viewport_size
            width, height = viewport_size["width"], viewport_size["height"]
            
            for _ in range(5):
                x = random.randint(100, width - 100)
                y = random.randint(100, height - 300)
                page.mouse.move(x, y, steps=random.randint(5, 10))
                time.sleep(random.uniform(0.3, 1.0))
            
            # Имитируем прокрутку страницы
            log_info("Имитация прокрутки страницы...")
            for _ in range(3):
                scroll_amount = random.randint(300, 800)
                page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                time.sleep(random.uniform(1.0, 2.0))
            
            # Проверяем загрузку контента
            log_info("Проверка загрузки контента...")
            try:
                # Проверяем заголовок товара
                product_title = page.query_selector("h1")
                if product_title:
                    log_info(f"Заголовок товара: {product_title.inner_text()}")
                
                # Проверяем наличие отзывов
                reviews_section = page.query_selector('[data-widget="webReviewList"], [data-widget="reviews"]')
                if reviews_section:
                    log_info("Секция отзывов найдена на странице!")
                else:
                    log_warning("Секция отзывов не найдена, возможно нужно прокрутить страницу дальше")
                
                page.screenshot(path="final_state.png")
                log_info("Сделан скриншот финального состояния страницы (final_state.png)")
                
            except Exception as e:
                log_error(f"Ошибка при проверке контента: {e}")
            
            # Даем пользователю время на визуальную проверку
            log_info("Тест завершен. Браузер закроется через 10 секунд...")
            time.sleep(10)
            
        except Exception as e:
            log_error(f"Ошибка при выполнении теста: {e}")
        finally:
            if 'browser' in locals():
                browser.close()

if __name__ == "__main__":
    run_test() 