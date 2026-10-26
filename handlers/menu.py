import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from keyboards.main import (
    main_menu_keyboard, main_reply_keyboard, 
    trading_menu_kb, learning_menu_kb, activities_menu_kb, profile_menu_kb
)
from config import ADMINS
from handlers.ads_display import show_ad_if_needed

logger = logging.getLogger(__name__)
router = Router()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

# --- Reply-кнопки ---
@router.message(F.text == "🏠 Главное меню")
async def reply_menu(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await message.answer("📌 <b>Главное меню:</b>", reply_markup=main_menu_keyboard(user_id, user_id in ADMINS), parse_mode="HTML")
    await message.answer("Выбери раздел ниже 👇", reply_markup=main_reply_keyboard())
    await show_ad_if_needed(message, is_admin=user_id in ADMINS)

@router.message(F.text == "📊 Анализ")
async def reply_analysis(message: Message, state: FSMContext):
    await state.clear()
    from handlers.analysis import analysis_menu
    class FakeCallback:
        def __init__(self, msg, user): self.message = msg; self.from_user = user
        async def answer(self, *args, **kwargs): pass
    await analysis_menu(FakeCallback(message, message.from_user), state)

@router.message(F.text == "💼 Торговля")
async def reply_trading(message: Message, state: FSMContext):
    await state.clear()
    from handlers.trading import trading_menu
    class FakeCallback:
        def __init__(self, msg, user): self.message = msg; self.from_user = user
        async def answer(self, *args, **kwargs): pass
    await trading_menu(FakeCallback(message, message.from_user), state)

@router.message(F.text == "🛒 Магазин")
async def reply_shop(message: Message, state: FSMContext):
    await state.clear()
    from handlers.shop import shop_menu
    class FakeCallback:
        def __init__(self, msg, user): self.message = msg; self.from_user = user
        async def answer(self, *args, **kwargs): pass
    await shop_menu(FakeCallback(message, message.from_user))

# --- Inline-кнопки ---
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await safe_edit(callback.message, "📌 <b>Главное меню:</b>", reply_markup=main_menu_keyboard(user_id, user_id in ADMINS))
    await callback.answer()

@router.callback_query(F.data == "menu_trading")
async def menu_trading(callback: CallbackQuery):
    text = "📈 <b>ТРЕЙДИНГ</b>\n\nАнализ, торговля и учет твоих сделок."
    await safe_edit(callback.message, text, reply_markup=trading_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_learning")
async def menu_learning(callback: CallbackQuery):
    text = "📚 <b>ОБУЧЕНИЕ И АНАЛИТИКА</b>\n\nСтратегии, книги и новости."
    await safe_edit(callback.message, text, reply_markup=learning_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_activities")
async def menu_activities(callback: CallbackQuery):
    text = "🎮 <b>АКТИВНОСТИ</b>\n\nБонусы, магазин и рефералы."
    await safe_edit(callback.message, text, reply_markup=activities_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    text = "💎 <b>ПРОФИЛЬ</b>\n\nПодписка, настройки и помощь."
    await safe_edit(callback.message, text, reply_markup=profile_menu_kb())
    await callback.answer()