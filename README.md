# Sexy Ozon Parser

Парсер отзывов товаров Ozon с антидетектом и имитацией человеческого поведения.

## Возможности

- Сбор отзывов о товарах с сайта Ozon
- Антидетект (обход обнаружения автоматизации)
- Имитация человеческого поведения при навигации
- Инкрементный парсинг (сбор только новых отзывов)
- Сохранение отзывов в JSON
- Многостраничный сбор отзывов с пагинацией

## Требования

- Python 3.8+
- Playwright
- Другие зависимости указаны в requirements.txt

## Использование

1. Установите зависимости:
```
pip install -r requirements.txt
```

2. Установите браузеры для Playwright:
```
playwright install
```

3. Запустите парсер:
```
python scheduled_parser.py
```

Для отладочного режима:
```
python scheduled_parser.py --debug
```

## Настройка

Настройки парсера находятся в файле config.py:
- Список URL товаров для сбора отзывов
- Максимальное количество отзывов для сбора
- Включение/отключение инкрементного режима
- Прокси-сервера (при необходимости)
- Тайм-ауты и задержки

## Структура проекта

- `src/parsers/` - модули парсеров
- `src/db/` - модули для работы с данными
- `src/utils/` - утилиты и вспомогательные функции
- `data/` - директория для сохранения собранных данных
- `logs/` - логи работы парсера

## Особенности

- Обработка разных форматов дат для корректного инкрементного сбора
- Надежная навигация между страницами отзывов
- Имитация человеческих действий (случайные задержки, прокрутка, движения мыши)
- Отказоустойчивость при ошибках сети и блокировках

## Лицензия

MIT

## Автор

Ваше имя / организация 