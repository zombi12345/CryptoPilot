import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import BooksStates
from services.rag import add_book, list_books, delete_book
from services.summarizer import summarize_book, format_book_summary
from database import (
    save_book_summary, get_book_summary, delete_book_summary,
)

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit(msg, text, reply_markup=None):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup)
        else:
            await msg.edit_text(text)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup)
            else:
                await msg.answer(text)
        except Exception:
            pass


def books_kb(books: list):
    kb = []
    for b in books:
        kb.append([InlineKeyboardButton(
            text=f"📖 {b['filename']} ({b['chunks']} чанков)",
            callback_data=f"book_view_{b['filename']}",
        )])
    kb.append([InlineKeyboardButton(text="📤 Загрузить книгу", callback_data="book_upload")])
    kb.append([InlineKeyboardButton(text="Меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


def book_view_kb(filename: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Конспект", callback_data=f"book_sum_{filename}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"book_del_{filename}")],
        [InlineKeyboardButton(text="Назад", callback_data="stub_books")],
    ])


@router.callback_query(F.data == "stub_books")
async def books_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    books = list_books(callback.from_user.id)
    if not books:
        text = (
            "Библиотека\n\n"
            "Пока пусто.\n\n"
            "Загрузи PDF или DOCX (до 10 МБ) — AI будет учитывать эти книги при анализе графиков."
        )
    else:
        text = (
            f"Библиотека ({len(books)} книг)\n\n"
            f"Эти книги AI использует при анализе графиков в разделе Анализ.\n\n"
            f"Выбери книгу:"
        )
    await safe_edit(callback.message, text, reply_markup=books_kb(books))
    await callback.answer()


@router.callback_query(F.data == "book_upload")
async def book_upload(callback: CallbackQuery, state: FSMContext):
    await safe_edit(
        callback.message,
        "Отправь файл PDF или DOCX (до 10 МБ).\n\n"
        "После загрузки AI сделает конспект книги (2-5 минут).\n\n"
        "/cancel для отмены.",
    )
    await state.set_state(BooksStates.waiting_file)
    await callback.answer()


@router.message(BooksStates.waiting_file, F.document)
async def book_file(message: Message, state: FSMContext):
    doc = message.document
    filename = doc.file_name or "book.pdf"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("pdf", "docx"):
        await message.answer("Только PDF или DOCX.")
        return
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await message.answer("Файл больше 10 МБ.")
        return

    msg = await message.answer("Шаг 1/2: Извлекаю текст и считаю embeddings...")
    file = await message.bot.get_file(doc.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    data = file_bytes.read()

    result = add_book(message.from_user.id, filename, data)
    if result.get("error"):
        await safe_edit(msg, f"Ошибка: {result['error']}")
        await state.clear()
        return

    await safe_edit(
        msg,
        f"Шаг 1/2 готово.\n"
        f"Символов: {result['chars']}\n"
        f"Чанков: {result['chunks']}\n\n"
        f"Шаг 2/2: AI делает конспект книги (2-5 минут)...",
    )

    summary = await summarize_book(message.from_user.id, filename, result["full_text"])
    if summary.get("error"):
        await message.answer(
            f"Книга загружена, но конспект не удался: {summary['error']}\n"
            f"AI будет использовать только RAG-выдержки."
        )
        await state.clear()
        return

    await save_book_summary(message.from_user.id, filename, summary)

    await message.answer(
        f"Книга полностью загружена.\n\n"
        f"Файл: {filename}\n"
        f"Глав: {summary.get('chapters_count', '?')}\n"
        f"Правил: {len(summary.get('all_rules', []))}\n"
        f"Паттернов: {len(summary.get('all_patterns', []))}\n\n"
        f"Теперь AI использует её при анализе графиков."
    )
    await state.clear()


@router.message(BooksStates.waiting_file)
async def book_need_file(message: Message):
    await message.answer("Отправь файл PDF или DOCX, или /cancel")


@router.callback_query(F.data.startswith("book_view_"))
async def book_view(callback: CallbackQuery):
    filename = callback.data.replace("book_view_", "")
    summary = await get_book_summary(callback.from_user.id, filename)
    status = "Конспект: есть" if summary else "Конспект: нет (только RAG)"
    text = f"Книга: {filename}\n{status}\n\nВыбери действие:"
    await safe_edit(callback.message, text, reply_markup=book_view_kb(filename))
    await callback.answer()


@router.callback_query(F.data.startswith("book_sum_"))
async def book_summary_view(callback: CallbackQuery):
    filename = callback.data.replace("book_sum_", "")
    summary = await get_book_summary(callback.from_user.id, filename)
    if not summary:
        await callback.answer("Конспекта нет", show_alert=True)
        return
    text = format_book_summary(summary)
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for p in parts:
            try:
                await callback.message.answer(p)
            except Exception:
                pass
        await callback.answer()
        return
    await safe_edit(callback.message, text, reply_markup=book_view_kb(filename))
    await callback.answer()


@router.callback_query(F.data.startswith("book_del_"))
async def book_delete(callback: CallbackQuery):
    filename = callback.data.replace("book_del_", "")
    ok = delete_book(callback.from_user.id, filename)
    await delete_book_summary(callback.from_user.id, filename)
    if ok:
        await callback.answer("Удалено")
    else:
        await callback.answer("Не найдено", show_alert=True)
    books = list_books(callback.from_user.id)
    text = f"Библиотека ({len(books)} книг)\n\nВыбери книгу:"
    if not books:
        text = "Библиотека пуста. Загрузи PDF или DOCX."
    await safe_edit(callback.message, text, reply_markup=books_kb(books))