from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_keyboard(user_id: int, is_admin: bool = False):
    kb = InlineKeyboardBuilder()
    kb.button(text="📈 Трейдинг", callback_data="menu_trading")
    kb.button(text="📚 Обучение", callback_data="menu_learning")
    kb.button(text="🎮 Активности", callback_data="menu_activities")
    kb.button(text="💎 Профиль", callback_data="menu_profile")
    
    if is_admin:
        kb.button(text="👑 Админ-панель", callback_data="stub_admin")
        
    kb.adjust(2)
    return kb.as_markup()

def trading_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Анализ графиков", callback_data="stub_analysis")],
        [InlineKeyboardButton(text="💼 Торговля", callback_data="stub_trading")],
        [InlineKeyboardButton(text="💰 Портфель", callback_data="stub_portfolio")],
        [InlineKeyboardButton(text="📔 Дневник сделок", callback_data="stub_journal")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

def learning_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Стратегии", callback_data="stub_strategies")],
        [InlineKeyboardButton(text="📚 Библиотека книг", callback_data="stub_books")],
        [InlineKeyboardButton(text="📰 Новости", callback_data="stub_news")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

def activities_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Ежедневный бонус", callback_data="stub_bonus")],
        [InlineKeyboardButton(text="🛒 Магазин", callback_data="stub_shop")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="stub_referral")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

def profile_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Подписка", callback_data="sub_menu")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="stub_settings")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="stub_help")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])

def main_reply_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="📊 Анализ"), KeyboardButton(text="💼 Торговля"), KeyboardButton(text="🛒 Магазин")]
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выбери раздел или напиши сообщение...",
    )
    return kb