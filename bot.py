import os
import sys
import asyncio
import logging
import tempfile
from pathlib import Path
from html import escape

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from converter import convert_book, SUPPORTED_FORMATS, is_archive
from ficbook import extract_fic_id, fetch_ficbook, save_ficbook_fb2, save_ficbook_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FORMAT_NAMES = {
    'epub': 'EPUB', 'pdf': 'PDF', 'mobi': 'MOBI',
    'fb2': 'FB2', 'docx': 'DOCX', 'txt': 'TXT',
    'rtf': 'RTF', 'djvu': 'DJVU', 'cbz': 'CBZ',
    'html': 'HTML', 'odt': 'ODT',
}

user_states = {}

GROUP_LINK = "\n\n📚 Группа с книгами: <a href=\"https://t.me/knigavbaku_28\">@knigavbaku_28</a>"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 <b>Book Converter Bot</b>\n\n"
        "Отправь мне файл книги или архив (ZIP/RAR), и я конвертирую его.\n\n"
        "Также могу скачать фанфик с <b>ficbook.net</b> в FB2 — "
        "просто пришли ссылку.\n\n"
        "Поддерживаемые форматы:\n"
        "EPUB, PDF, MOBI, FB2, DOCX, TXT, RTF, DJVU, CBZ, HTML, ODT\n\n"
        "Просто отправь файл или ссылку!\n\n"
        "📚 <b>Группа с книгами:</b> <a href=\"https://t.me/knigavbaku_28\">@knigavbaku_28</a>\n"
        "✍️ <b>Печатная машина:</b> <a href=\"https://t.me/Vkooker8\">@Vkooker8</a>",
        parse_mode="HTML"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>Как использовать:</b>\n\n"
        "1. Отправь файл книги (.epub, .pdf, .mobi, .fb2 и др.)\n"
        "2. Выбери формат для конвертации\n"
        "3. Получи конвертированный файл\n\n"
        "Также можно отправлять архивы ZIP/RAR с книгами.\n"
        "Если в архиве несколько книг — все будут конвертированы.",
        parse_mode="HTML"
    )


async def handle_ficbook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    fic_id = extract_fic_id(text)
    if not fic_id:
        return

    status_msg = await update.message.reply_text("⏳ Загружаю данные фанфика с ficbook.net...")

    try:
        loop = asyncio.get_event_loop()
        fic_data = await loop.run_in_executor(None, fetch_ficbook, text)

        user_states[update.message.from_user.id] = {
            "fic_data": fic_data,
            "fic_id": fic_id,
        }

        buttons = [
            [
                InlineKeyboardButton("📄 FB2", callback_data="fic:fb2"),
                InlineKeyboardButton("📕 PDF", callback_data="fic:pdf"),
            ]
        ]

        await status_msg.edit_text(
            f"📖 <b>{escape(fic_data['title'])}</b>\n"
            f"✍️ {escape(fic_data['author'])}\n"
            f"📝 {len(fic_data['chapters'])} частей\n\n"
            f"Выбери формат:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ficbook error: {e}")
        await status_msg.edit_text(f"❌ Ошибка: {escape(str(e))}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    filename = doc.file_name or "unknown"
    ext = Path(filename).suffix.lower()
    all_supported = SUPPORTED_FORMATS | {'.zip', '.rar'}

    if ext not in all_supported:
        await update.message.reply_text(
            f"❌ Формат <code>{ext}</code> не поддерживается.\n"
            f"Поддерживаемые: {', '.join(sorted(SUPPORTED_FORMATS))}\n"
            f"Архивы: .zip, .rar",
            parse_mode="HTML"
        )
        return

    status_msg = await update.message.reply_text("⏳ Скачиваю файл...")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        tmpdir = tempfile.mkdtemp(prefix="bookbot_")
        filepath = os.path.join(tmpdir, filename)
        await tg_file.download_to_drive(filepath)

        if ext in SUPPORTED_FORMATS:
            available = [f.lstrip('.') for f in SUPPORTED_FORMATS if f != ext]
        else:
            available = sorted(f.lstrip('.') for f in SUPPORTED_FORMATS)

        buttons = []
        row = []
        for fmt in available:
            row.append(InlineKeyboardButton(
                FORMAT_NAMES.get(fmt, fmt.upper()),
                callback_data=f"conv:{fmt}"
            ))
            if len(row) == 3:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        user_states[update.message.from_user.id] = {
            "filepath": filepath,
            "tmpdir": tmpdir,
            "filename": filename,
        }

        format_list = "\n".join(
            [f"  • {FORMAT_NAMES.get(f, f.upper())}" for f in available]
        )

        await status_msg.edit_text(
            f"✅ Файл <b>{filename}</b> скачан.\n\n"
            f"Выбери формат для конвертации:\n{format_list}{GROUP_LINK}",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        await status_msg.edit_text(f"❌ Ошибка скачивания: {escape(str(e))}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        logger.warning("CallbackQuery is None")
        return
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"query.answer() failed: {e}")

    data = query.data or ""
    user_id = query.from_user.id
    logger.info(f"Callback received: data={data} user={user_id}")

    try:
        chat_id = query.message.chat_id if query.message else query.from_user.id
    except Exception:
        chat_id = query.from_user.id

    if query.message:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=query.message.message_id
            )
        except Exception:
            pass

    if data.startswith("fic:"):
        fmt = data.split(":")[1]
        state = user_states.get(user_id)
        if not state or "fic_data" not in state:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Сессия устарела. Отправь ссылку заново."
            )
            return

        fic_data = state["fic_data"]
        fic_id = state["fic_id"]

        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔄 Скачиваю <b>{escape(fic_data['title'])}</b> в формате {fmt.upper()}...",
            parse_mode="HTML"
        )

        try:
            loop = asyncio.get_event_loop()
            tmpdir = tempfile.mkdtemp(prefix="ficbook_")

            if fmt == "fb2":
                filepath = await loop.run_in_executor(
                    None, save_ficbook_fb2, fic_data, fic_id, tmpdir
                )
            else:
                filepath = await loop.run_in_executor(
                    None, save_ficbook_pdf, fic_data, fic_id, tmpdir
                )

            filename = Path(filepath).name
            with open(filepath, "rb") as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=filename,
                    caption=f"📖 {filename}"
                )
            await status_msg.edit_text(
                f"✅ Готово: <b>{escape(filename)}</b>{GROUP_LINK}",
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"Ficbook download error: {e}")
            await status_msg.edit_text(
                f"❌ Ошибка:\n<pre>{escape(str(e))}</pre>",
                parse_mode="HTML"
            )
        return

    if not data.startswith("conv:"):
        return

    parts = data.split(":")
    if len(parts) < 2:
        return

    target_format = parts[1]

    state = user_states.get(user_id)
    if not state:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Сессия устарела. Отправь файл заново."
        )
        return

    filepath = state["filepath"]

    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"🔄 Конвертирую <b>{state['filename']}</b> → <b>{FORMAT_NAMES.get(target_format, target_format.upper())}</b>...",
        parse_mode="HTML"
    )

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, convert_book, filepath, target_format)

        if isinstance(result, list):
            for r in result:
                with open(r, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=Path(r).name,
                        caption=f"✅ {Path(r).name}"
                    )
            await status_msg.edit_text(
                f"✅ Конвертация завершена! Файлов: {len(result)}{GROUP_LINK}",
                parse_mode="HTML"
            )
        else:
            with open(result, 'rb') as f:
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=Path(result).name,
                    caption=f"✅ {Path(result).name}"
                )
            await status_msg.edit_text(
                f"✅ Готово! Файл отправлен выше.{GROUP_LINK}",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Conversion error: {e}")
        await status_msg.edit_text(f"❌ Ошибка конвертации:\n<pre>{escape(str(e))}</pre>",
                                  parse_mode="HTML")


def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


def main():
    load_env()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or token == "СЮДА_ВПИШИ_СВОЙ_ТОКЕН":
        print("❌ Открой .env файл и впиши свой токен бота")
        print("   Файл: .env")
        return

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ficbook))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_callback), group=1)

    print("🤖 Book Converter Bot запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
