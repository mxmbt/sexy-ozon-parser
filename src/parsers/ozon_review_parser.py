import re
import time
import random
import uuid
from datetime import datetime
from playwright.sync_api import sync_playwright
from src.utils.config import (
    HEADLESS, USER_AGENT, REQUEST_TIMEOUT, DEFAULT_DELAY,
    MAX_REVIEWS_PER_PRODUCT, MAX_RETRIES, get_random_delay,
    INCREMENTAL_PARSING
)
from src.utils.logger import log_info, log_error, log_warning, log_debug
from src.database.json_storage import ReviewsStorage

class OzonReviewParser:
    def __init__(self, debug_mode=False):
        """Инициализация парсера отзывов Озона"""
        self.db = ReviewsStorage()
        self.playwright = None
        self.browser = None
        self.context = None
        self.debug_mode = debug_mode
        
    def _extract_product_id(self, url):
        """
        Извлечение ID продукта из URL
        
        Args:
            url (str): URL продукта
            
        Returns:
            str: ID продукта или None, если не удалось извлечь
        """
        # Пытаемся извлечь ID товара из URL, например из https://www.ozon.ru/product/item-name-123456/
        match = re.search(r'/product/.*?-(\d+)/?', url)
        if match:
            return match.group(1)
            
        # Альтернативный формат URL с параметром
        match = re.search(r'id=(\d+)', url)
        if match:
            return match.group(1)
            
        return None
    
    def _initialize_browser(self):
        """
        Инициализация браузера и контекста с улучшенными настройками для обхода защиты
        
        Returns:
            bool: True, если инициализация прошла успешно, иначе False
        """
        try:
            self.playwright = sync_playwright().start()
            
            # Запускаем браузер с дополнительными аргументами для обхода защиты
            self.browser = self.playwright.chromium.launch(
                headless=HEADLESS,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-features=BlockInsecurePrivateNetworkRequests',
                    f'--user-agent={USER_AGENT}'
                ]
            )
            
            # Настраиваем контекст браузера с более реалистичными параметрами
            self.context = self.browser.new_context(
                user_agent=USER_AGENT,
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
            
            # Устанавливаем тайм-аут для всех операций
            self.context.set_default_timeout(REQUEST_TIMEOUT)
            
            # Переопределяем webdriver свойства для обхода обнаружения
            self._bypass_detection()
            
            log_info("Браузер и контекст успешно инициализированы")
            return True
        except Exception as e:
            log_error(f"Ошибка при инициализации браузера: {e}", exc_info=True)
            return False
    
    def _bypass_detection(self):
        """Обход обнаружения автоматизации через изменение свойств navigator и webdriver"""
        try:
            # Получаем страницу для внедрения скриптов
            page = self.context.new_page()
            
            # Внедряем скрипт для обхода webdriver detection
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => false
                });
                
                // Перегрузка свойств, используемых для обнаружения автоматизации
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
                
                // Скрываем что страница автоматизирована
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({state: Notification.permission}) :
                        originalQuery(parameters)
                );
            """)
            
            # Закрываем временную страницу
            page.close()
            log_info("Антидетект скрипты успешно добавлены")
        except Exception as e:
            log_error(f"Ошибка при добавлении антидетект скриптов: {e}")
    
    def _human_like_scroll(self, page, max_scrolls=5):
        """
        Имитирует прокрутку страницы человеком
        
        Args:
            page: Объект страницы Playwright
            max_scrolls: Максимальное количество прокруток
            
        Returns:
            bool: True, если прокрутка успешна
        """
        try:
            log_info("Имитация прокрутки страницы человеком")
            
            # Получаем высоту страницы
            page_height = page.evaluate("() => document.body.scrollHeight")
            viewport_height = page.evaluate("() => window.innerHeight")
            
            # Определяем количество прокруток
            scrolls = min(max_scrolls, max(1, page_height // viewport_height))
            
            for i in range(scrolls):
                # Случайная величина прокрутки
                scroll_amount = random.randint(
                    viewport_height // 2, 
                    viewport_height + random.randint(10, 100)
                )
                
                # Эмулируем плавную прокрутку
                page.evaluate(f"""() => {{
                    window.scrollBy({{
                        top: {scroll_amount},
                        left: 0,
                        behavior: 'smooth'
                    }});
                }}""")
                
                # Случайная задержка между прокрутками
                time.sleep(random.uniform(0.5, 2.0))
                
                # Иногда немного прокручиваем назад, как это делают люди
                if random.random() < 0.3:
                    page.evaluate(f"""() => {{
                        window.scrollBy({{
                            top: -{random.randint(50, 200)},
                            left: 0,
                            behavior: 'smooth'
                        }});
                    }}""")
                    time.sleep(random.uniform(0.3, 0.7))
            
            # В конце прокручиваем до нужного места
            page.evaluate("""() => {
                // Пытаемся найти заголовок секции отзывов
                const reviewsHeader = Array.from(document.querySelectorAll('h2')).find(h => 
                    h.textContent.includes('Отзыв') || h.textContent.includes('отзыв'));
                
                if (reviewsHeader) {
                    reviewsHeader.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return true;
                }
                
                // Альтернативный поиск по атрибутам
                const reviewsSection = document.querySelector('[data-widget="webReviewList"]') || 
                                      document.querySelector('[data-widget="reviews"]');
                
                if (reviewsSection) {
                    reviewsSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    return true;
                }
            }""")
            
            return True
        except Exception as e:
            log_error(f"Ошибка при эмуляции прокрутки: {e}", exc_info=True)
            return False

    def _human_like_move(self, page):
        """
        Имитирует движения мыши человека по странице
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если движения выполнены успешно
        """
        try:
            # Получаем размеры окна
            viewport_size = page.viewport_size
            width, height = viewport_size["width"], viewport_size["height"]
            
            # Выполняем несколько случайных движений мыши
            for _ in range(random.randint(3, 7)):
                # Случайные координаты
                x = random.randint(100, width - 100)
                y = random.randint(100, height - 300)
                
                # Скорость движения (чем больше, тем медленнее)
                speed = random.randint(3, 8)
                
                # Перемещаем мышь
                page.mouse.move(x, y, steps=speed)
                
                # Случайная задержка
                time.sleep(random.uniform(0.1, 0.8))
                
                # С вероятностью 30% делаем клик
                if random.random() < 0.3:
                    page.mouse.click(x, y)
                    time.sleep(random.uniform(0.3, 1.0))
            
            return True
        except Exception as e:
            log_error(f"Ошибка при эмуляции движений мыши: {e}")
            return False
            
    def _open_page(self, page, url):
        """
        Открывает URL в браузере с обработкой ошибок
        
        Args:
            page: Объект страницы Playwright
            url: URL страницы для открытия
            
        Returns:
            bool: True, если страница открыта успешно
        """
        try:
            log_info(f"Переход на страницу: {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT)
            page.wait_for_load_state("networkidle", timeout=REQUEST_TIMEOUT)
            
            # Случайная задержка после загрузки страницы
            time.sleep(get_random_delay())
            
            # Проверяем, есть ли ограничение доступа и пытаемся его обойти
            self._solve_access_restriction(page)
            
            return True
        except Exception as e:
            log_error(f"Ошибка при открытии страницы: {e}", exc_info=True)
            
            # Делаем скриншот в режиме отладки
            if self.debug_mode:
                try:
                    page.screenshot(path=f"debug_page_error_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                    log_debug("Сделан скриншот страницы с ошибкой")
                except Exception as screenshot_error:
                    log_debug(f"Не удалось сделать скриншот: {screenshot_error}")
            
            return False
            
    def _solve_access_restriction(self, page):
        """
        Пытается решить проблему с ограничением доступа
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если ограничение преодолено
        """
        try:
            # Проверяем, есть ли ограничение доступа
            if page.get_by_text("Доступ ограничен").is_visible():
                log_warning("Обнаружено ограничение доступа, пытаемся его обойти")
                
                # Нажимаем кнопку "Обновить"
                refresh_button = page.get_by_role("button", name="Обновить")
                if refresh_button.is_visible():
                    # Делаем небольшую задержку
                    time.sleep(random.uniform(1.0, 2.0))
                    log_info("Нажимаем кнопку 'Обновить'")
                    refresh_button.click()
                    
                    # Ждем загрузки страницы
                    page.wait_for_load_state("networkidle")
                    time.sleep(get_random_delay() * 2)
                    
                    # Проверяем, решилась ли проблема
                    if not page.get_by_text("Доступ ограничен").is_visible():
                        log_info("Ограничение доступа преодолено успешно")
                        return True
                    else:
                        log_warning("Не удалось преодолеть ограничение доступа")
                        return False
            
            # Если нет ограничения, возвращаем True
            return True
        except Exception as e:
            log_error(f"Ошибка при попытке обойти ограничение доступа: {e}")
            return False
    
    def _click_reviews_tab(self, page):
        """
        Ищет и нажимает на вкладку "Отзывы" на странице товара
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если удалось нажать на вкладку, иначе False
        """
        try:
            log_info("Поиск вкладки с отзывами...")
            
            # Прямой переход по URL с /reviews/ имеет приоритет
            current_url = page.url
            product_id = self._extract_product_id(current_url)
            
            if product_id:
                # Формируем URL страницы отзывов
                # Удаляем все параметры из URL
                base_url = current_url.split('?')[0]
                if base_url.endswith('/'):
                    reviews_url = f"{base_url}reviews/"
                else:
                    reviews_url = f"{base_url}/reviews/"
                
                # Проверяем, если мы уже на странице отзывов
                if "/reviews" in current_url:
                    log_info("Уже находимся на странице отзывов")
                    return True
                
                log_info(f"Прямой переход на страницу отзывов: {reviews_url}")
                try:
                    page.goto(reviews_url, wait_until="domcontentloaded", timeout=20000)
                    # Используем меньший таймаут для networkidle
                    page.wait_for_load_state("networkidle", timeout=15000)
                    time.sleep(random.uniform(1.0, 2.0))
                    
                    new_url = page.url
                    if "/reviews" in new_url:
                        log_info("Успешно перешли на страницу отзывов")
                        return True
                    else:
                        log_warning(f"Переход по прямой ссылке не удался. Новый URL: {new_url}")
                except Exception as e:
                    log_warning(f"Ошибка при прямом переходе на страницу отзывов: {e}")
                    # Продолжаем с другими методами, не прерываем выполнение
            
            # Пробуем искать по тексту "Отзывы" или "reviews"
            text_selectors = [
                'a:has-text("Отзывы")',
                'a:has-text("отзывы")',
                'a:has-text("ОТЗЫВЫ")',
                'a:has-text("Reviews")',
                'a:has-text("reviews")',
                'div:has-text("Отзывы") >> a',
                'a:has-text("Все отзывы")',
                'a[href*="/reviews"]',
                'a[href*="tab=reviews"]'
            ]
            
            for selector in text_selectors:
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        text = element.inner_text().strip()
                        href = element.get_attribute("href") or ""
                        log_info(f"Найден элемент отзывов: селектор={selector}, текст={text}, href={href}")
                        
                        # Прокручиваем к элементу и кликаем
                        element.scroll_into_view_if_needed()
                        time.sleep(random.uniform(0.5, 1.0))
                        element.click()
                        log_info("Нажали на элемент с отзывами")
                        
                        # Используем уменьшенный таймаут для networkidle
                        try:
                            page.wait_for_load_state("networkidle", timeout=15000)
                        except Exception as e:
                            log_warning(f"Таймаут при ожидании загрузки после клика: {e}")
                            # Но продолжаем выполнение, т.к. страница могла загрузиться
                        
                        time.sleep(random.uniform(1.0, 2.0))
                        return True
                except Exception as e:
                    log_debug(f"Ошибка при поиске селектора {selector}: {e}")
            
            # Если не удалось найти элементы, ищем по JavaScript элементы, содержащие "отзывы"
            try:
                review_element = page.evaluate("""() => {
                    // Ищем любые элементы, содержащие текст отзывы
                    const elements = Array.from(document.querySelectorAll('a, button, div, span'))
                        .filter(el => el.innerText && 
                               (el.innerText.toLowerCase().includes('отзыв') || 
                                el.innerText.toLowerCase().includes('review')));
                    
                    // Ищем элементы с ссылками на reviews
                    const links = Array.from(document.querySelectorAll('a[href*="reviews"], a[href*="отзыв"]'));
                    
                    // Возвращаем первый найденный элемент
                    return links.length > 0 ? links[0] : (elements.length > 0 ? elements[0] : null);
                }""")
                
                if review_element:
                    log_info("Найден элемент отзывов с помощью JavaScript")
                    # Кликаем по найденному элементу
                    page.evaluate("element => element.click()", review_element)
                    log_info("Нажали на элемент отзывов с помощью JavaScript")
                    
                    # Используем уменьшенный таймаут
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception as e:
                        log_warning(f"Таймаут при ожидании загрузки после JavaScript-клика: {e}")
                    
                    time.sleep(random.uniform(1.0, 2.0))
                    return True
            except Exception as e:
                log_debug(f"Ошибка при поиске отзывов через JavaScript: {e}")
            
            # Если ни один из методов не сработал, пробуем перейти на страницу с якорем #reviews или #comments
            try:
                anchor_url = f"{current_url.split('#')[0]}#reviews"
                log_info(f"Пробуем перейти по URL с якорем: {anchor_url}")
                page.goto(anchor_url, wait_until="domcontentloaded")
                time.sleep(random.uniform(1.0, 2.0))
                return True  # Пробуем продолжить, даже если переход по якорю не очевиден
            except Exception as e:
                log_debug(f"Ошибка при переходе по URL с якорем: {e}")
            
            log_warning("Не удалось найти или активировать вкладку с отзывами")
            
            # Делаем скриншот только в режиме отладки
            if self.debug_mode:
                try:
                    screenshot_path = f"debug_no_reviews_tab_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                    page.screenshot(path=screenshot_path)
                    log_debug(f"Сделан скриншот при отсутствии вкладки отзывов: {screenshot_path}")
                except Exception as screenshot_err:
                    log_debug(f"Не удалось сделать скриншот: {screenshot_err}")
            
            return False
            
        except Exception as e:
            log_error(f"Ошибка при поиске и нажатии на вкладку отзывов: {e}", exc_info=True)
            return False
    
    def _scroll_to_reviews(self, page):
        """
        Прокрутка страницы до секции с отзывами с имитацией поведения человека
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если прокрутка прошла успешно, иначе False
        """
        try:
            # Ждем загрузки контента страницы, но с ограниченным таймаутом
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception as e:
                log_warning(f"Таймаут при ожидании загрузки страницы: {e}")
                # Продолжаем выполнение, даже если произошел таймаут
            
            # Имитируем поведение человека перед прокруткой
            self._human_like_move(page)
            
            # Проверяем, нужно ли решать проблему с ограничением доступа
            if page.get_by_text("Доступ ограничен").is_visible():
                if not self._solve_access_restriction(page):
                    log_error("Не удалось преодолеть ограничение доступа")
                    return False
            
            # Проверяем, есть ли на странице элементы с отзывами
            review_indicators = [
                'div[data-review-uuid]',
                'div[data-widget="webReviewList"]',
                'div[itemprop="review"]',
                'div.review-item',
                'div:has-text("Отзывы покупателей")',
                'h2:has-text("Отзывы")',
                'div:has-text("У этого товара пока нет отзывов")'
            ]
            
            for selector in review_indicators:
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        log_info(f"Найден индикатор отзывов: {selector}")
                        element.scroll_into_view_if_needed()
                        time.sleep(random.uniform(0.5, 1.0))
                        return True
                except Exception as e:
                    log_debug(f"Ошибка при поиске индикатора отзывов {selector}: {e}")
            
            # Если не нашли прямых индикаторов, используем JavaScript для поиска текста "отзыв"
            try:
                review_element = page.evaluate("""() => {
                    const elements = Array.from(document.querySelectorAll('*'))
                        .filter(el => el.innerText && 
                               (el.innerText.toLowerCase().includes('отзыв') || 
                                el.innerText.toLowerCase().includes('review')));
                    
                    // Находим самый видимый элемент
                    for (const el of elements) {
                        const rect = el.getBoundingClientRect();
                        if (rect.top >= 0 && rect.left >= 0 && 
                            rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) && 
                            rect.right <= (window.innerWidth || document.documentElement.clientWidth)) {
                            return el;
                        }
                    }
                    
                    return elements.length > 0 ? elements[0] : null;
                }""")
                
                if review_element:
                    log_info("Найден элемент, связанный с отзывами, с помощью JavaScript")
                    page.evaluate("element => element.scrollIntoView({behavior: 'smooth', block: 'center'})", review_element)
                    time.sleep(random.uniform(0.5, 1.0))
                    return True
            except Exception as e:
                log_debug(f"Ошибка при поиске элементов отзывов через JavaScript: {e}")
            
            # Если не удалось найти отзывы, пробуем общую прокрутку
            log_info("Не удалось найти конкретные элементы отзывов, выполняю общую прокрутку")
            return self._human_like_scroll(page)
        except Exception as e:
            log_error(f"Ошибка при прокрутке до секции с отзывами: {e}", exc_info=True)
            return False
    
    def _close_browser(self):
        """Закрытие браузера и контекста"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
                
            log_info("Браузер и контекст закрыты")
        except Exception as e:
            log_error(f"Ошибка при закрытии браузера: {e}", exc_info=True)
    
    def _click_show_more_reviews(self, page):
        """
        Нажатие на кнопку "Показать больше отзывов", если она есть
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если кнопка найдена и нажата, иначе False
        """
        try:
            # Ищем кнопку "Показать больше отзывов"
            show_more_button = page.query_selector('button:has-text("Показать еще")')
            
            if show_more_button and show_more_button.is_visible():
                log_info("Нажатие на кнопку 'Показать еще отзывы'")
                show_more_button.click()
                
                # Ждем загрузки дополнительных отзывов
                page.wait_for_load_state("networkidle")
                time.sleep(get_random_delay())
                return True
            
            return False
        except Exception as e:
            log_warning(f"Не удалось нажать на кнопку 'Показать еще': {e}")
            return False
    
    def _navigate_to_next_reviews_page(self, page):
        """
        Переход на следующую страницу отзывов
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            bool: True, если переход выполнен успешно, иначе False
        """
        try:
            log_info("Попытка перехода на следующую страницу отзывов")
            
            # Первый метод: ищем и нажимаем кнопку "Дальше"
            log_info("Поиск кнопки 'Дальше'...")
            
            # Делаем скриншот для отладки
            if self.debug_mode:
                screenshot_path = f"before_next_page_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                page.screenshot(path=screenshot_path)
                log_debug(f"Скриншот перед переходом на следующую страницу: {screenshot_path}")
            
            # Получаем текущий URL для дальнейшего сравнения
            current_url = page.url
            
            # Список возможных селекторов для кнопки "Дальше"
            next_button_selectors = [
                'div.b2122-a8:has-text("Дальше")',            # Селектор из старого кода
                'button:has-text("Дальше")',                  # Кнопка по тексту
                'div:has-text("Дальше"):not(:has(div))',      # Текст "Дальше" в div
                'a:has-text("Дальше")',                       # Ссылка с текстом "Дальше"
                'div.gp7_32:has-text("Дальше")',              # Специфический класс
                '.paginator a.xg9_32',                        # Пагинация
                'div[data-widget="paginator"] a:last-child',  # Последняя ссылка в пагинаторе
                '[data-widget="paginator"] [data-test-id="next-page"]', # Тестовый ID для кнопки пагинации
                '[data-test-id="next-page"]'                  # Тестовый ID кнопки "Следующая страница"
            ]
            
            # Проверяем каждый селектор
            next_button = None
            for selector in next_button_selectors:
                try:
                    element = page.query_selector(selector)
                    if element and element.is_visible():
                        log_info(f"Найдена кнопка 'Дальше' по селектору: {selector}")
                        next_button = element
                        break
                except Exception as e:
                    log_debug(f"Ошибка при поиске кнопки 'Дальше' по селектору {selector}: {e}")
            
            # Если не нашли кнопку по селекторам, ищем через JavaScript
            if not next_button:
                log_info("Поиск кнопки 'Дальше' с помощью JavaScript...")
                next_button_info = page.evaluate("""() => {
                    // Ищем элементы с текстом "Дальше" или "Следующая"
                    const elements = Array.from(document.querySelectorAll('a, button, div'))
                        .filter(el => {
                            const text = el.innerText?.trim().toLowerCase() || '';
                            return text === 'дальше' || text === 'следующая' || text === 'вперед' || 
                                   text === '→' || text === 'next' || text === '>' || text.includes('след');
                        });
                    
                    if (elements.length > 0) {
                        const element = elements[0];
                        // Возвращаем XPath для элемента
                        let path = '';
                        let temp = element;
                        while (temp && temp.nodeType === 1) {
                            let idx = 0;
                            let sibling = temp;
                            while (sibling) {
                                if (sibling.nodeType === 1 && sibling.tagName === temp.tagName) {
                                    idx++;
                                }
                                sibling = sibling.previousSibling;
                            }
                            const tagName = temp.tagName.toLowerCase();
                            const step = idx ? `${tagName}[${idx}]` : tagName;
                            path = `/${step}${path}`;
                            temp = temp.parentNode;
                        }
                        return {
                            xpath: path,
                            text: element.innerText?.trim(),
                            isClickable: element.tagName === 'A' || element.tagName === 'BUTTON'
                        };
                    }
                    
                    // Ищем элементы с арабской цифрой, большей 1 (потенциальные страницы)
                    const pageNumbers = Array.from(document.querySelectorAll('a, span, div'))
                        .filter(el => {
                            const text = el.innerText?.trim() || '';
                            return /^[2-9][0-9]*$/.test(text); // Число больше 1
                        })
                        .sort((a, b) => parseInt(a.innerText) - parseInt(b.innerText));
                    
                    if (pageNumbers.length > 0) {
                        // Берем элемент с наименьшим номером, большим 1
                        const nextPageElement = pageNumbers[0];
                        let path = '';
                        let temp = nextPageElement;
                        while (temp && temp.nodeType === 1) {
                            let idx = 0;
                            let sibling = temp;
                            while (sibling) {
                                if (sibling.nodeType === 1 && sibling.tagName === temp.tagName) {
                                    idx++;
                                }
                                sibling = sibling.previousSibling;
                            }
                            const tagName = temp.tagName.toLowerCase();
                            const step = idx ? `${tagName}[${idx}]` : tagName;
                            path = `/${step}${path}`;
                            temp = temp.parentNode;
                        }
                        return {
                            xpath: path,
                            text: nextPageElement.innerText?.trim(),
                            isClickable: nextPageElement.tagName === 'A' || nextPageElement.tagName === 'BUTTON'
                        };
                    }
                    
                    return null;
                }""")
                
                if next_button_info:
                    log_info(f"Найдена кнопка пагинации с текстом: {next_button_info.get('text', 'Неизвестно')}")
                    try:
                        xpath = next_button_info.get('xpath')
                        if xpath:
                            next_button = page.locator(f"xpath={xpath}")
                    except Exception as e:
                        log_warning(f"Ошибка при получении элемента по XPath: {e}")
            
            # Если нашли кнопку, нажимаем на неё
            if next_button:
                log_info("Нажимаю на кнопку 'Дальше'")
                
                # Прокручиваем к кнопке и делаем её видимой
                next_button.scroll_into_view_if_needed()
                time.sleep(random.uniform(0.5, 1.0))
                
                # Нажимаем на кнопку
                next_button.click()
                log_info("Выполнен клик по кнопке 'Дальше'")
                
                # Ждем загрузки страницы
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception as e:
                    log_warning(f"Таймаут при ожидании загрузки страницы: {e}")
                
                # Проверяем, изменился ли URL после клика
                new_url = page.url
                if new_url != current_url:
                    log_info(f"Успешный переход на следующую страницу. Новый URL: {new_url}")
                    
                    # Имитируем поведение человека после загрузки новой страницы
                    self._human_like_scroll(page)
                    self._human_like_move(page)
                    
                    time.sleep(random.uniform(1.0, 2.0))
                    return True
                else:
                    log_warning("URL не изменился после клика, возможно, кнопка не сработала")
            
            # Второй метод: пробуем построить URL напрямую, если не удалось найти кнопку
            log_info("Попытка построить URL для следующей страницы...")
            
            # Если есть ?page=X в URL, заменяем X на X+1
            if "page=" in current_url:
                match = re.search(r'page=(\d+)', current_url)
                if match:
                    current_page = int(match.group(1))
                    next_page = current_page + 1
                    log_info(f"Текущая страница: {current_page}, переход на страницу {next_page}")
                    
                    next_url = re.sub(r'page=\d+', f'page={next_page}', current_url)
                    log_info(f"Переход по прямому URL: {next_url}")
                    
                    try:
                        page.goto(next_url, wait_until="domcontentloaded")
                        page.wait_for_load_state("networkidle", timeout=15000)
                        
                        # Проверяем, изменился ли URL после перехода
                        if page.url != current_url:
                            log_info(f"Успешный переход по прямому URL на страницу {next_page}")
                            
                            # Имитируем поведение человека
                            self._human_like_scroll(page)
                            self._human_like_move(page)
                            
                            time.sleep(random.uniform(1.0, 2.0))
                            return True
                        else:
                            log_warning("URL не изменился после перехода, возможно, страница не существует")
                    except Exception as e:
                        log_error(f"Ошибка при переходе по прямому URL: {e}")
            else:
                # Если это первая страница, добавляем page=2
                next_url = None
                if "?" in current_url:
                    next_url = f"{current_url}&page=2"
                else:
                    next_url = f"{current_url}?page=2"
                
                log_info(f"Переход по прямому URL на вторую страницу: {next_url}")
                
                try:
                    page.goto(next_url, wait_until="domcontentloaded")
                    page.wait_for_load_state("networkidle", timeout=15000)
                    
                    # Проверяем, изменился ли URL после перехода
                    if page.url != current_url:
                        log_info("Успешный переход на вторую страницу по прямому URL")
                        
                        # Имитируем поведение человека
                        self._human_like_scroll(page)
                        self._human_like_move(page)
                        
                        time.sleep(random.uniform(1.0, 2.0))
                        return True
                    else:
                        log_warning("URL не изменился после перехода, возможно, страница не существует")
                except Exception as e:
                    log_error(f"Ошибка при переходе по прямому URL: {e}")
            
            # Если не удалось перейти ни одним способом
            log_warning("Не удалось перейти на следующую страницу отзывов")
            
            # Делаем скриншот для отладки
            if self.debug_mode:
                try:
                    screenshot_path = f"failed_next_page_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
                    page.screenshot(path=screenshot_path)
                    log_debug(f"Скриншот при неудачной попытке перехода: {screenshot_path}")
                except Exception as screenshot_err:
                    log_debug(f"Не удалось сделать скриншот: {screenshot_err}")
            
            return False
            
        except Exception as e:
            log_error(f"Ошибка при переходе на следующую страницу: {e}", exc_info=True)
            return False
    
    def _parse_review_element(self, review_element, product_id, product_url):
        """
        Парсит отдельный элемент отзыва и извлекает все данные.
        
        Args:
            review_element: Элемент DOM, содержащий отзыв
            product_id (str): ID продукта
            product_url (str): URL продукта
            
        Returns:
            dict: Данные отзыва или None в случае ошибки
        """
        try:
            # Генерируем уникальный ID для отзыва
            review_id = str(uuid.uuid4())
            
            # Если элемент имеет атрибут data-review-uuid, используем его
            uuid_attr = review_element.get_attribute('data-review-uuid')
            if uuid_attr:
                review_id = uuid_attr
                log_debug(f"Найден ID отзыва в атрибуте: {review_id}")
            
            # СТРОГО ищем текст отзыва по указанной структуре
            text = ""
            try:
                # Точная структура: div.px7_31.y4p_31 > div.x7p_31 > div > span.p7x_31
                text_container = review_element.query_selector('div[class*="px7_"][class*="y4p_"] > div[class*="x7p_"] > div > span[class*="p7x_"]')
                
                if text_container:
                    text = text_container.inner_text().strip()
                    if text:
                        log_debug(f"Найден текст отзыва по точной структуре: {text[:30]}...")
                    
                    # Проверяем, не является ли текст служебным сообщением
                    if "Пользователь предпочёл скрыть свои данные" in text or "Количество в упаковке" in text:
                        text = ""
                        log_debug("Отфильтрован некорректный текст отзыва (служебное сообщение)")
            except Exception as e:
                log_debug(f"Ошибка при извлечении текста отзыва: {e}")
            
            # СТРОГО ищем автора отзыва
            author = ""
            try:
                # Точная структура: span.p8u_31
                author_element = review_element.query_selector('span[class*="p8u_"]')
                
                if author_element:
                    author = author_element.inner_text().strip()
                    log_debug(f"Найден автор отзыва: {author}")
                    
                    # Проверяем, не является ли автор служебным сообщением
                    if "Пользователь предпочёл скрыть свои данные" in author:
                        log_debug("Автор отзыва скрыт системой")
            except Exception as e:
                log_debug(f"Ошибка при извлечении автора отзыва: {e}")
            
            # СТРОГО ищем дату отзыва
            date = ""
            try:
                # Пробуем найти дату по новому селектору
                date_element = review_element.query_selector('div[class*="x5p_"]')
                
                # Если не нашли, пробуем по старому селектору
                if not date_element:
                    date_element = review_element.query_selector('div[class*="rv1_"]')
                
                if date_element:
                    date = date_element.inner_text().strip()
                    log_debug(f"Найдена дата отзыва: {date}")
                else:
                    log_debug("Не удалось найти элемент с датой отзыва")
            except Exception as e:
                log_debug(f"Ошибка при извлечении даты отзыва: {e}")
            
            # СТРОГО ищем вариант товара
            product_variant = ""
            try:
                # Точная структура: a.y3p_31
                variant_element = review_element.query_selector('a[class*="y3p_"]')
                
                if variant_element:
                    product_variant = variant_element.inner_text().strip()
                    log_debug(f"Найден вариант товара: {product_variant}")
            except Exception as e:
                log_debug(f"Ошибка при извлечении варианта товара: {e}")
            
            # СТРОГО ищем рейтинг (количество звезд)
            rating = 0
            try:
                # На основе предоставленной структуры HTML, точное определение контейнера
                # Первичный селектор: div.p6x_31 > div.a5d25-a
                rating_container = review_element.query_selector('div[class*="p6x_"] > div[class*="a5d25-a"]')
                
                if not rating_container:
                    # Альтернативный поиск, если точная структура не найдена
                    rating_container = review_element.query_selector('div[class*="p6x_"], div[class*="a5d25-a"]')
                
                if rating_container:
                    log_debug("Найден контейнер для рейтинга")
                    
                    # Используем JavaScript для определения количества оранжевых звезд
                    filled_stars = rating_container.evaluate("""(container) => {
                        // Ищем все SVG элементы внутри контейнера
                        const svgElements = Array.from(container.querySelectorAll('svg'));
                        
                        // Считаем количество SVG с оранжевым цветом (rgb(255, 165, 0))
                        const filledStars = svgElements.filter(svg => {
                            const style = svg.getAttribute('style') || '';
                            return style.includes('rgb(255, 165, 0)') || 
                                  style.includes('rgb(255,165,0)') ||
                                  style.includes('color: rgb(255, 165, 0)') ||
                                  style.includes('orange');
                        });
                        
                        return filledStars.length;
                    }""")
                    
                    if filled_stars and 0 < filled_stars <= 5:
                        rating = filled_stars
                        log_debug(f"Найдено {filled_stars} оранжевых звезд с помощью точного селектора")
                    else:
                        log_debug("Не удалось определить рейтинг по точному критерию, пробуем альтернативные методы")
                        
                        # Способ 2: Подсчет через CSS селекторы для разных форматов цвета
                        selectors = [
                            'svg[style*="color: rgb(255"]',
                            'svg[style*="orange"]',
                            'svg[style*="rgb(255, 165"]',
                            'svg[style*="#f"]',
                            'svg[fill*="#f"]',
                            'svg[fill="currentColor"]'
                        ]
                        
                        for selector in selectors:
                            stars = rating_container.query_selector_all(selector)
                            if stars and 0 < len(stars) <= 5:
                                rating = len(stars)
                                log_debug(f"Найдено {rating} SVG-звезд по селектору {selector}")
                                break
                        
                        # Способ 3: Подсчет через JavaScript с более широкими критериями
                        if rating == 0:
                            js_count = rating_container.evaluate("""(container) => {
                                // Ищем все SVG элементы внутри контейнера
                                const svgElements = container.querySelectorAll('svg');
                                
                                // Подсчитываем SVG с оранжевым цветом (любой оттенок)
                                let count = 0;
                                for (const svg of svgElements) {
                                    const style = window.getComputedStyle(svg);
                                    const colorStyle = svg.getAttribute('style') || '';
                                    const fillColor = svg.getAttribute('fill') || '';
                                    
                                    // Проверяем различные форматы цвета: RGB, HEX, названия
                                    if (
                                        (style.color && style.color.includes('255')) || // rgb содержит 255 (красный)
                                        colorStyle.includes('rgb(255') || 
                                        colorStyle.includes('orange') || 
                                        colorStyle.includes('gold') ||
                                        colorStyle.includes('#f') || // hex цвета с буквой f
                                        fillColor.includes('#f') ||
                                        fillColor.includes('orange') ||
                                        fillColor.includes('gold')
                                    ) {
                                        count++;
                                    }
                                    
                                    // Также проверяем, есть ли path с fill="currentColor"
                                    const paths = svg.querySelectorAll('path[fill="currentColor"]');
                                    if (paths.length > 0 && (
                                        colorStyle.includes('rgb(255') || 
                                        colorStyle.includes('orange') || 
                                        colorStyle.includes('gold') ||
                                        colorStyle.includes('#f')
                                    )) {
                                        if (count === 0) count++; // Добавляем, только если еще не считали эту звезду
                                    }
                                }
                                
                                return count;
                            }""")
                            
                            if js_count and 0 < js_count <= 5:
                                rating = js_count
                                log_debug(f"Найдено {rating} SVG-звезд с помощью расширенного JavaScript")
                        
                        # Способ 4: Если все не помогло, просто считаем количество SVG (для стабильности)
                        if rating == 0:
                            # Считаем первые SVG элементы, которые не имеют rgba в стиле (обычно это заполненные звезды)
                            filled_count = rating_container.evaluate("""(container) => {
                                const svgs = Array.from(container.querySelectorAll('svg'));
                                // Отфильтровываем SVG элементы, у которых нет rgba в стиле
                                return svgs.filter(svg => {
                                    const style = svg.getAttribute('style') || '';
                                    return !style.includes('rgba');
                                }).length;
                            }""")
                            
                            if filled_count and 0 < filled_count <= 5:
                                rating = filled_count
                                log_debug(f"Определено примерное количество звезд: {rating} (путем исключения неокрашенных)")
                    
                    log_debug(f"Итоговый рейтинг отзыва: {rating}")
            except Exception as e:
                log_error(f"Ошибка при извлечении рейтинга отзыва: {e}", exc_info=True)
            
            # Создаем словарь с данными отзыва
            review_data = {
                "review_id": review_id,
                "product_id": product_id,
                "product_url": product_url,
                "author": author,
                "rating": rating,
                "date": date,
                "text": text,
                "product_variant": product_variant
            }
            
            return review_data
            
        except Exception as e:
            log_error(f"Ошибка при парсинге элемента отзыва: {e}")
            return None
    
    def _parse_review(self, review_element, product_id, product_url):
        """
        Прокси к _parse_review_element для обратной совместимости
        
        Args:
            review_element: Элемент DOM, содержащий отзыв
            product_id (str): ID продукта
            product_url (str): URL продукта
            
        Returns:
            dict: Данные отзыва или None в случае ошибки
        """
        return self._parse_review_element(review_element, product_id, product_url)
    
    def _find_review_container(self, page):
        """
        Находит контейнер с отзывами на странице
        
        Args:
            page: Объект страницы Playwright
            
        Returns:
            tuple: (container_element, selector) или (None, None), если не найден
        """
        try:
            log_info("Поиск контейнера с отзывами...")
            
            # Расширенный список селекторов для поиска контейнера с отзывами
            container_selectors = [
                # Селекторы из скриншота
                'div.r9u_32',          # Контейнер с отзывами (из скриншота)
                'div:has(span.y4p_32)', # Контейнер, содержащий элемент с текстом отзыва
                'div.pz0_32',          # Еще один контейнер из скриншота
                
                # Селекторы, связанные с виджетами отзывов
                'div[data-widget="webReviews"]',
                'div[data-widget="webReviewsList"]',
                'div[data-widget="webReviewList"]',
                'div[data-widget="reviews"]',
                'div[data-widget="webReviewContainer"]',
                'div[data-widget="searchResultsV2"]',
                
                # Селекторы по классам и структуре
                'div.widget-search-result-container',
                'div.review-grid',
                
                # Селекторы контейнеров, содержащих отзывы
                'div:has(div[data-review-uuid])',
                'div:has([itemprop="review"])',
                
                # Более общие селекторы
                'div.container-reviews',
                'div:has-text("Отзывы о товаре")',
                'div:has(div:has-text("Отзывы покупателей"))'
            ]
            
            # Проверяем видимые элементы сначала
            for selector in container_selectors:
                log_info(f"Проверка селектора: {selector}")
                container = page.query_selector(selector)
                if container and container.is_visible():
                    log_info(f"Найден контейнер отзывов по селектору: {selector}")
                    return container, selector
            
            # Если не нашли по селекторам, проверяем наличие элементов с классами из скриншота
            possible_review_classes = [
                'r9u_32',     # Контейнер отзыва
                'pz0_32',     # Контейнер элементов отзыва
                'y4p_32',     # Элемент с текстом отзыва
                'vp5_32'      # Элемент с рейтингом (звезды)
            ]
            
            # Ищем элементы с характерными классами
            for class_name in possible_review_classes:
                elements = page.query_selector_all(f'.{class_name}')
                if elements and len(elements) > 0:
                    log_info(f"Найдены элементы с классом {class_name} (количество: {len(elements)})")
                    
                    # Для класса текста отзыва ищем родительский контейнер
                    if class_name == 'y4p_32':
                        parent = elements[0].evaluate("""(element) => {
                            // Ищем родителя, который может быть контейнером всех отзывов
                            let parent = element.parentElement;
                            for (let i = 0; i < 5; i++) { // Проверяем до 5 уровней вверх
                                if (!parent) return null;
                                // Проверяем, содержит ли родитель другие похожие элементы
                                const siblings = parent.querySelectorAll('.y4p_32, .vp5_32, [class*="r9u_"], [class*="pz0_"]');
                                if (siblings.length > 1) {
                                    return parent;
                                }
                                parent = parent.parentElement;
                            }
                            return null;
                        }""")
                        
                        if parent:
                            log_info("Найден родительский контейнер для элементов отзывов")
                            return parent, "parent-of-y4p_32"
                    
                    # Для контейнера отзывов просто возвращаем первый элемент
                    if class_name == 'r9u_32' or class_name == 'pz0_32':
                        log_info(f"Возвращаем контейнер с классом {class_name}")
                        return elements[0], f".{class_name}"
            
            # Если не нашли по классам, ищем элементы с текстом, который может быть отзывом
            log_info("Поиск элементов, содержащих длинный текст (возможные отзывы)")
            
            # Используем JavaScript для поиска элементов с длинным текстом
            potential_reviews = page.evaluate("""() => {
                // Ищем элементы с непустым текстом длиной более 50 символов
                const potentialReviews = [];
                
                // Все элементы с видимым текстом
                const elements = Array.from(document.querySelectorAll('*'));
                for (const el of elements) {
                    const text = el.innerText?.trim();
                    // Проверяем, что текст достаточно длинный и не является навигационным/служебным
                    if (text && text.length > 50 && 
                        !el.tagName.match(/^(HTML|BODY|HEAD|SCRIPT|STYLE|LINK|META)$/i) &&
                        !text.includes('JavaScript') && 
                        !text.includes('DOCTYPE') &&
                        !el.closest('header') && 
                        !el.closest('footer') && 
                        !el.closest('nav')) {
                        
                        // Добавляем путь до элемента для идентификации
                        let path = '';
                        let node = el;
                        while (node) {
                            if (node.id) {
                                path = `#${node.id} > ${path}`;
                                break;
                            } else if (node.className) {
                                path = `.${node.className.split(' ').join('.')} > ${path}`;
                            } else {
                                path = `${node.tagName.toLowerCase()} > ${path}`;
                            }
                            node = node.parentElement;
                        }
                        
                        potentialReviews.push({
                            path: path,
                            textLength: text.length,
                            textSample: text.substring(0, 100) + '...'
                        });
                    }
                }
                
                // Сортируем по длине текста (более длинные сначала)
                return potentialReviews.sort((a, b) => b.textLength - a.textLength).slice(0, 5);
            }""")
            
            if potential_reviews and len(potential_reviews) > 0:
                log_info("Найдены потенциальные элементы с текстом отзывов:")
                for i, review in enumerate(potential_reviews):
                    log_info(f"  {i+1}. Путь: {review['path']}, длина текста: {review['textLength']}, пример: {review['textSample']}")
                
                # Пробуем найти контейнер для первого потенциального отзыва
                first_review_path = potential_reviews[0]['path']
                try:
                    # Извлекаем селектор из пути
                    selector = first_review_path.split(' > ')[0].strip()
                    log_info(f"Пробуем использовать селектор: {selector}")
                    
                    element = page.query_selector(selector)
                    if element:
                        log_info(f"Найден элемент с потенциальным отзывом: {selector}")
                        return element, "potential-review-text"
                except Exception as e:
                    log_debug(f"Ошибка при обработке потенциального отзыва: {e}")
            
            # Если все ещё не нашли, ищем любые элементы с текстом "отзыв" и делаем скриншот страницы
            log_warning("Не удалось найти контейнер с отзывами")
            
            # Делаем скриншот страницы для отладки
            screenshot_path = "reviews_page_debug.png"
            page.screenshot(path=screenshot_path)
            log_info(f"Сделан скриншот страницы для отладки: {screenshot_path}")
            
            return None, None
        
        except Exception as e:
            log_error(f"Ошибка при поиске контейнера с отзывами: {e}", exc_info=True)
            return None, None
    
    def _collect_reviews_from_page(self, page, product_id, product_url):
        """
        Собирает отзывы со страницы, находя элементы с атрибутом data-review-uuid.
        
        Args:
            page: объект страницы Playwright
            product_id: ID продукта
            product_url: URL продукта
            
        Returns:
            list: список собранных отзывов
        """
        log_info("Сбор отзывов со страницы...")
        reviews = []
        
        try:
            # Делаем скриншот страницы для отладки
            screenshot_path = f"debug_reviews_page_{datetime.now().strftime('%Y%m%d%H%M%S')}.png"
            page.screenshot(path=screenshot_path)
            log_debug(f"Сделан скриншот страницы отзывов: {screenshot_path}")
            
            # Сохраняем HTML для анализа структуры
            html_path = f"debug_reviews_page_{datetime.now().strftime('%Y%m%d%H%M%S')}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(page.content())
            log_debug(f"Сохранен HTML страницы отзывов: {html_path}")
            
            # Логируем текущий URL для отладки
            log_info(f"Текущий URL при сборе отзывов: {page.url}")
            
            # Ждем немного, чтобы страница полностью загрузилась
            time.sleep(random.uniform(1.0, 2.0))
            
            # Проверяем наличие сообщения "нет отзывов"
            if page.query_selector('div:has-text("У этого товара пока нет отзывов")') or page.query_selector('div:has-text("Еще нет отзывов")'):
                log_info("На странице есть сообщение 'Нет отзывов'")
                return []
            
            # Ждем появления элементов отзывов с таймаутом
            try:
                page.wait_for_selector('div[data-review-uuid], div[data-widget="webReviewList"] > div', timeout=10000)
                log_info("Найдены элементы отзывов на странице")
            except Exception as e:
                log_warning(f"Таймаут при ожидании элементов отзывов: {e}")
            
            # Ищем элементы отзывов напрямую по атрибуту data-review-uuid
            review_elements = page.query_selector_all('div[data-review-uuid]')
            log_info(f"Найдено {len(review_elements)} элементов с атрибутом data-review-uuid")
            
            # Проверяем, что мы нашли отзывы
            if not review_elements or len(review_elements) == 0:
                log_warning("Не найдено отзывов с атрибутом data-review-uuid, ищем альтернативными способами")
                
                # Список альтернативных селекторов для поиска отзывов
                alternative_selectors = [
                    'div[data-widget="webReviewList"] > div',
                    'div[itemprop="review"]',
                    'div.rv3_32 > div',  # Из скриншота
                    'div.r0o_32',        # Из скриншота
                    'div.rw5_32',        # Из скриншота
                    'div:has(span.y4p_32)',  # Контейнер с текстом отзыва
                    'div:has(div.vp5_32)',   # Контейнер с рейтингом (звезды)
                    'div:has(div.r0o_32)',   # Контейнер с данными автора
                    'div.review-item',
                    'div.rc1_32'          # Еще один класс из структуры
                ]
                
                # Пробуем каждый селектор
                for selector in alternative_selectors:
                    try:
                        elements = page.query_selector_all(selector)
                        if elements and len(elements) > 0:
                            log_info(f"Найдено {len(elements)} элементов по селектору {selector}")
                            review_elements = elements
                            break
                    except Exception as e:
                        log_debug(f"Ошибка при поиске элементов по селектору {selector}: {e}")
                
                # Если все еще не нашли элементы, ищем с помощью JavaScript
                if not review_elements or len(review_elements) == 0:
                    log_warning("Не найдено отзывов по альтернативным селекторам, поиск через JavaScript")
                    
                    # Пробуем найти элементы через JavaScript
                    js_elements = page.evaluate("""() => {
                        // Функция для поиска потенциальных контейнеров отзывов
                        function findPotentialReviews() {
                            // Ищем элементы с классами, содержащими определенные паттерны
                            const classPatterns = ['review', 'otziv', 'rv', 'r0o', 'y4p', 'vp5'];
                            
                            // Находим все элементы с подходящими классами
                            const elements = [];
                            for (const pattern of classPatterns) {
                                const matches = document.querySelectorAll(`[class*="${pattern}"]`);
                                for (const match of matches) {
                                    elements.push(match);
                                }
                            }
                            
                            // Ищем контейнеры, которые могут содержать несколько похожих элементов
                            const containers = new Map();
                            for (const el of elements) {
                                // Проверяем 3 уровня родителей
                                let parent = el.parentElement;
                                for (let i = 0; i < 3 && parent; i++) {
                                    if (!containers.has(parent)) {
                                        containers.set(parent, 0);
                                    }
                                    containers.set(parent, containers.get(parent) + 1);
                                    parent = parent.parentElement;
                                }
                            }
                            
                            // Находим контейнеры с наибольшим количеством подходящих элементов
                            const potentialContainers = Array.from(containers.entries())
                                .filter(([_, count]) => count > 2)  // Минимум 3 подходящих элемента
                                .sort(([_, countA], [__, countB]) => countB - countA);
                            
                            return potentialContainers.length > 0 ? 
                                potentialContainers[0][0].outerHTML : null;
                        }
                        
                        return findPotentialReviews();
                    }""")
                    
                    if js_elements:
                        log_info("Найдены потенциальные элементы отзывов через JavaScript")
                        # Здесь мы не можем напрямую использовать результат, 
                        # так как JavaScript вернул HTML строку, а не элементы DOM
                        log_debug("JavaScript вернул HTML потенциальных отзывов, но не элементы DOM")
                        
                        # Повторяем проверку наличия элементов после JavaScript-анализа
                        for selector in alternative_selectors:
                            elements = page.query_selector_all(selector)
                            if elements and len(elements) > 0:
                                log_info(f"После JavaScript-анализа найдено {len(elements)} элементов по селектору {selector}")
                                review_elements = elements
                                break
            
            # Если нашли элементы отзывов, обрабатываем их
            if review_elements and len(review_elements) > 0:
                log_info(f"Найдено {len(review_elements)} элементов отзывов на странице")
                
                # Обрабатываем каждый элемент отзыва
                for element in review_elements:
                    review_data = self._parse_review_element(element, product_id, product_url)
                    if review_data:
                        reviews.append(review_data)
                
                log_info(f"Успешно собрано {len(reviews)} отзывов со страницы")
                return reviews
            else:
                log_warning("Не удалось найти элементы отзывов на странице")
                
                # Проверяем наличие индикаторов отсутствия отзывов
                no_reviews_selectors = [
                    'div:has-text("У этого товара пока нет отзывов")',
                    'div:has-text("Отзывов пока нет")',
                    'div:has-text("Нет отзывов")',
                    'div:has-text("Еще нет отзывов")'
                ]
                
                for selector in no_reviews_selectors:
                    if page.query_selector(selector):
                        log_info(f"Найдено сообщение об отсутствии отзывов: {selector}")
                        return []
                
                return []
                
        except Exception as e:
            log_error(f"Ошибка при сборе отзывов со страницы: {e}", exc_info=True)
            return []
    
    def _validate_review_elements(self, elements):
        """
        Проверяет, что найденные элементы действительно являются отзывами
        
        Args:
            elements: список элементов для проверки
            
        Returns:
            bool: True, если элементы похожи на отзывы
        """
        # Если элементов слишком мало, это вряд ли список отзывов
        if len(elements) < 2:
            return False
            
        # Проверяем первые несколько элементов на наличие типичных признаков отзыва
        valid_elements = 0
        for i in range(min(3, len(elements))):
            element = elements[i]
            
            try:
                # Проверяем наличие текста отзыва
                text_elements = element.query_selector_all('span[class*="y4p_"], div[class*="r8p_"], div[class*="wp4_"]')
                has_text = len(text_elements) > 0 and any(el.inner_text().strip() for el in text_elements)
                
                # Проверяем наличие звездного рейтинга
                rating_elements = element.query_selector_all('div[class*="vp5_"], svg[fill="#f9c000"], svg[fill="#ffb800"]')
                has_rating = len(rating_elements) > 0
                
                # Проверяем наличие даты или имени автора
                author_date_elements = element.query_selector_all('div[class*="rv0_"], div[class*="rv1_"], div[class*="r1c_"], div[class*="x5p_"]')
                has_author_date = len(author_date_elements) > 0
                
                # Считаем элемент валидным, если есть хотя бы два из трех признаков
                if (has_text and has_rating) or (has_text and has_author_date) or (has_rating and has_author_date):
                    valid_elements += 1
            except Exception as e:
                log_debug(f"Ошибка при проверке элемента на валидность: {e}")
                
        # Если большинство проверенных элементов похожи на отзывы, считаем всю группу валидной
        return valid_elements >= min(2, len(elements))
    
    def _is_newer_review(self, review, last_review_date, last_review_ids=None):
        """
        Проверяет, является ли отзыв новее последнего собранного отзыва.
        
        Args:
            review (dict): Отзыв для проверки
            last_review_date (str): Дата последнего собранного отзыва
            last_review_ids (list): Список ID последних собранных отзывов
            
        Returns:
            bool: True, если отзыв новее или еще не собран, False в противном случае
        """
        # Если нет данных о последнем отзыве, считаем, что отзыв новый
        if not last_review_date:
            return True
            
        # Сначала проверяем ID отзыва
        if last_review_ids and 'review_id' in review:
            if review['review_id'] in last_review_ids:
                log_debug(f"Отзыв с ID {review['review_id']} уже собран")
                return False
                
        # Если дата отзыва не указана, считаем, что он новый
        if 'date' not in review:
            return True
            
        try:
            # Обрабатываем разные форматы дат
            review_date_str = review['date']
            last_date_str = last_review_date
            
            # Функция для преобразования строки в дату
            def parse_date(date_str):
                # Если формат DD.MM.YYYY
                if re.match(r'\d{1,2}\.\d{1,2}\.\d{4}', date_str):
                    day, month, year = map(int, date_str.split('.'))
                    return datetime(year, month, day)
                
                # Если формат "30 марта 2025" или похожий
                months_ru = {
                    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
                    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
                }
                
                match = re.match(r'(\d{1,2})\s+([а-яА-Я]+)\s+(\d{4})', date_str)
                if match:
                    day = int(match.group(1))
                    month_name = match.group(2).lower()
                    year = int(match.group(3))
                    
                    if month_name in months_ru:
                        month = months_ru[month_name]
                        return datetime(year, month, day)
                
                # Если дата в формате ISO (YYYY-MM-DD)
                try:
                    return datetime.fromisoformat(date_str)
                except ValueError:
                    pass
                
                # Если формат DD/MM/YYYY
                if re.match(r'\d{1,2}/\d{1,2}/\d{4}', date_str):
                    day, month, year = map(int, date_str.split('/'))
                    return datetime(year, month, day)
                
                # Если ничего не подошло, используем текущую дату
                log_warning(f"Неизвестный формат даты: {date_str}, используем текущую дату")
                return datetime.now()
            
            # Конвертируем строки в объекты datetime
            review_date = parse_date(review_date_str)
            last_date = parse_date(last_date_str)
            
            # Отзыв новее, если его дата больше даты последнего отзыва
            return review_date >= last_date
        except Exception as e:
            log_warning(f"Ошибка при сравнении дат отзывов: {e}")
            # В случае ошибки считаем, что отзыв новый
            return True
    
    def parse_product_reviews(self, product_url, max_reviews=None, incremental=None):
        """
        Основной метод для парсинга отзывов о продукте.
        
        Args:
            product_url (str): URL страницы продукта
            max_reviews (int, optional): Максимальное количество отзывов для сбора
            incremental (bool, optional): Флаг инкрементного парсинга
            
        Returns:
            list: Список собранных отзывов
        """
        # Если значения не указаны явно, используем значения из конфигурации
        if max_reviews is None:
            max_reviews = MAX_REVIEWS_PER_PRODUCT
            
        if incremental is None:
            incremental = INCREMENTAL_PARSING
            
        log_info(f"Запуск парсинга отзывов: {product_url}")
        log_info(f"Режим: {'инкрементный' if incremental else 'полный'}")
        log_info(f"Максимальное количество отзывов: {max_reviews}")
        
        # Извлекаем ID продукта из URL
        product_id = self._extract_product_id(product_url)
        if not product_id:
            log_error(f"Не удалось извлечь ID продукта из URL: {product_url}")
            return []
        
        log_info(f"ID продукта: {product_id}")
        
        # Для инкрементного парсинга получаем дату последнего отзыва и список ID
        last_review_date = None
        last_review_ids = []
        
        if incremental:
            last_review_date = self.db.get_last_review_date(product_id)
            last_review_ids = self.db.get_last_review_ids(product_id)
            
            if last_review_date:
                log_info(f"Дата последнего собранного отзыва: {last_review_date}")
                log_info(f"Количество сохраненных ID отзывов: {len(last_review_ids)}")
            else:
                log_info("Нет данных о предыдущих отзывах, выполняем полный парсинг")
        
        # Инициализируем браузер
        if not self.browser:
            self._initialize_browser()
        
        # Открываем новую страницу
        page = self.context.new_page()
        
        all_reviews = []
        try:
            # Формируем URL страницы отзывов (просто добавляем /reviews/)
            base_url = product_url.split('?')[0]
            if base_url.endswith('/'):
                reviews_url = f"{base_url}reviews/"
            else:
                reviews_url = f"{base_url}/reviews/"
            
            log_info(f"Переход напрямую на страницу отзывов: {reviews_url}")
            
            # Открываем страницу отзывов
            if not self._open_page(page, reviews_url):
                log_error("Не удалось открыть страницу отзывов, пробуем основной URL")
                
                # Если не удалось открыть страницу отзывов, пробуем основной URL
                if not self._open_page(page, product_url):
                    log_error("Не удалось открыть основную страницу продукта")
                    return []
                
                # Пытаемся перейти на вкладку отзывов
                log_info("Поиск и клик по вкладке с отзывами")
                if not self._click_reviews_tab(page):
                    log_error("Не удалось найти вкладку с отзывами")
                    return []
            
            # Выполняем прокрутку для лучшей загрузки контента
            self._human_like_scroll(page)
            
            # Сохраняем все необработанные отзывы со всех страниц
            raw_reviews = []
            
            # Проходим по всем страницам отзывов и собираем их
            page_num = 1
            stop_parsing = False
            
            while not stop_parsing:
                log_info(f"Обработка страницы отзывов #{page_num}")
                
                # Собираем отзывы с текущей страницы
                page_reviews = self._collect_reviews_from_page(page, product_id, product_url)
                
                # Сохраняем необработанные отзывы
                raw_reviews.extend(page_reviews)
                
                log_info(f"Собрано {len(page_reviews)} отзывов на странице #{page_num}")
                
                if not page_reviews:
                    log_info("На этой странице не найдено отзывов, завершаем парсинг")
                    break
                
                # Проверяем ограничение по количеству для сырых отзывов
                if max_reviews and len(raw_reviews) >= max_reviews:
                    log_info(f"Достигнут лимит в {max_reviews} отзывов (до фильтрации)")
                    break
                
                # Попробуем перейти на следующую страницу
                if not self._navigate_to_next_reviews_page(page):
                    log_info("Больше нет страниц с отзывами")
                    break
                
                # Увеличиваем номер страницы и делаем паузу перед обработкой следующей
                page_num += 1
                log_info(f"Переход к обработке страницы отзывов #{page_num}")
                time.sleep(random.uniform(1.0, 2.0))
            
            log_info(f"Всего собрано {len(raw_reviews)} отзывов со всех страниц (до фильтрации)")
            
            # Фильтруем отзывы для инкрементного парсинга
            if incremental and last_review_date and raw_reviews:
                # Проверяем каждый отзыв
                new_reviews = []
                for review in raw_reviews:
                    if self._is_newer_review(review, last_review_date, last_review_ids):
                        new_reviews.append(review)
                
                log_info(f"После фильтрации по дате осталось {len(new_reviews)} новых отзывов из {len(raw_reviews)}")
                all_reviews = new_reviews
            else:
                all_reviews = raw_reviews
                
        except Exception as e:
            log_error(f"Ошибка при парсинге отзывов: {e}", exc_info=True)
            # Делаем скриншот только в режиме отладки
            if self.debug_mode:
                page.screenshot(path=f"debug_parsing_error_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                
        finally:
            # Закрываем страницу
            page.close()
        
        # Сохраняем собранные отзывы
        if all_reviews:
            saved_count = self.db.save_reviews(all_reviews)
            log_info(f"Сохранено {saved_count} новых отзывов из {len(all_reviews)} собранных")
        else:
            log_info("Не удалось собрать ни одного отзыва")
        
        return all_reviews
    
    def parse_multiple_products(self, product_urls):
        """
        Парсинг отзывов для нескольких продуктов
        
        Args:
            product_urls (list): Список URL продуктов
            
        Returns:
            dict: Результаты парсинга (URL -> количество отзывов)
        """
        results = {}
        
        for url in product_urls:
            try:
                reviews = self.parse_product_reviews(url)
                results[url] = len(reviews)
                
                # Добавляем случайную задержку между запросами
                time.sleep(get_random_delay() * 2)
            except Exception as e:
                log_error(f"Ошибка при парсинге отзывов для {url}: {e}", exc_info=True)
                results[url] = 0
        
        return results
    
    def close(self):
        """Закрытие хранилища данных"""
        self.db.close() 