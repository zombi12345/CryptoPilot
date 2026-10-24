from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard(user_id: int, is_admin: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="Анализ", callback_data="stub_analysis")
    kb.button(text="Библиотека", callback_data="stub_books")
    kb.button(text="Стратегии", callback_data="stub_strategies")
    kb.button(text="Торговля", callback_data="stub_trading")
    kb.button(text="Настройки", callback_data="stub_settings")
    kb.button(text="Помощь", callback_data="stub_help")
    if is_admin:
        kb.button(text="Админ", callback_data="stub_admin")
    kb.adjust(2)
    return kb.as_markup()


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Меню")]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напиши сообщение или нажми Меню",
    )
    return kb