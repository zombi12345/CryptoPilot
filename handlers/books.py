import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

@router.callback_query(F.data == "stub_books")
async def books_menu(callback: CallbackQuery):
    text = (
        "📚 <b>БИБЛИОТЕКА</b>\n\n"
        "⚠️ <b>Раздел временно недоступен.</b>\n\n"
        "Загрузка книг и RAG-поиск работают только в локальной версии бота. "
        "На сервере Render мы отключили эту функцию из-за ограничений памяти.\n\n"
        "Приносим извинения за неудобства!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()