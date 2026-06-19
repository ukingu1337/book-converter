# Book Converter Bot

Telegram-бот для конвертации книг между форматами.

## Поддерживаемые форматы

**Книги:** EPUB, PDF, MOBI, FB2, DOCX, TXT, RTF, DJVU, CBZ, HTML, ODT

**Архивы:** ZIP, RAR (автоматическая распаковка)

## Установка

### 1. Установи Calibre (нужен `ebook-convert`)

**Windows:**
Скачай с https://calibre-ebook.com/download и добавь в PATH.

**Linux:**
```bash
sudo apt install calibre
```

**macOS:**
```bash
brew install calibre
```

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3. Получи токен бота

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Создай нового бота: `/newbot`
3. Скопируй токен

### 4. Запусти

```bash
# Linux/macOS
export TELEGRAM_BOT_TOKEN="your_token_here"
python bot.py

# Windows PowerShell
$env:TELEGRAM_BOT_TOKEN="your_token_here"
python bot.py
```

## Использование

1. Отправь боту файл книги или архив
2. Выбери формат для конвертации
3. Получи конвертированный файл

## Примеры

- Отправил `.epub` → выбрал PDF → получил PDF
- Отправил `.zip` с 3 книгами → выбрал MOBI → получил 3 MOBI-файла
- Отправил `.fb2` → выбрал EPUB → получил EPUB
