import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()


def help_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_help")
async def help_menu(callback: CallbackQuery):
    text = (
        "Помощь\n\n"
        "АНАЛИЗ — отправь фото графика, AI даст прогноз с учётом книг.\n\n"
        "БИБЛИОТЕКА — загрузи PDF/DOCX, AI будет использовать при анализе.\n\n"
        "СТРАТЕГИИ — пресеты, бэктест на истории.\n\n"
        "ТОРГОВЛЯ — RiskGuard + demo testnet. Реальные деньги не используются.\n\n"
        "НАСТРОЙКИ — профиль и лимиты.\n\n"
        "Все прогнозы не являются инвестиционной рекомендацией."
    )
    await callback.message.edit_text(text, reply_markup=help_kb())
    await callback.answer()