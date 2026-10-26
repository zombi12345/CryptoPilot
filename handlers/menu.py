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
    from database import check_and_increment_ai
    can_use, current, limit = await check_and_increment_ai(message.from_user.id)
    if not can_use:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Купить подписку", callback_data="sub_menu")]])
        return await message.answer(f"🚫 Лимит AI исчерпан ({current}/{limit}). Купи подписку Premium или обратись к админу.", reply_markup=kb)
    await message.answer(f"📊 <b>АНАЛИЗ ГРАФИКОВ</b>\n\nИспользовано запросов: {current}/{limit}\n\nОтправь скриншот графика или /cancel", reply_markup=main_menu_keyboard(message.from_user.id, message.from_user.id in ADMINS), parse_mode="HTML")
    from states import AnalysisStates
    await state.set_state(AnalysisStates.waiting_photo)

@router.message(F.text == "💼 Торговля")
async def reply_trading(message: Message, state: FSMContext):
    await state.clear()
    from database import get_user
    user = await get_user(message.from_user.id)
    is_paid = user.get("is_paid", False) if user else False
    text = "💼 <b>ТОРГОВЛЯ</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    if not is_paid:
        text += "⚠️ <b>Доступен только Demo (Testnet)</b>\n<i>Для перехода на реал нужна подписка Premium.</i>\n\n"
    else:
        text += "Режим: <b>Demo (Testnet)</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="trade_balance")],
        [InlineKeyboardButton(text="📊 Позиции", callback_data="trade_positions")],
        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="📜 История", callback_data="trade_history")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🛒 Магазин")
async def reply_shop(message: Message, state: FSMContext):
    await state.clear()
    from database import get_user, get_pool
    user = await get_user(message.from_user.id)
    balance = user.get("balance_coins", 0) if user else 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        items = await conn.fetch("SELECT * FROM shop_items WHERE is_active = TRUE")
    text = f"🛒 <b>МАГАЗИН</b>\n➖➖➖➖➖➖➖➖➖➖\n💰 Твой баланс: <b>{balance} монет</b>\n\n"
    if not items:
        text += "Пока пусто. Заходи позже!"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
        return await message.answer(text, reply_markup=kb, parse_mode="HTML")
    kb = []
    for item in items:
        kb.append([InlineKeyboardButton(text=f"{item['title']} — {item['price']} монет", callback_data=f"buy_item_{item['id']}")])
    kb.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")

# --- Inline-кнопки ---
@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await safe_edit(callback.message, "📌 <b>Главное меню:</b>", reply_markup=main_menu_keyboard(user_id, user_id in ADMINS))
    await callback.answer()

@router.callback_query(F.data == "menu_trading")
async def menu_trading(callback: CallbackQuery):
    await safe_edit(callback.message, "📈 <b>ТРЕЙДИНГ</b>\n\nАнализ, торговля и учет твоих сделок.", reply_markup=trading_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_learning")
async def menu_learning(callback: CallbackQuery):
    await safe_edit(callback.message, "📚 <b>ОБУЧЕНИЕ И АНАЛИТИКА</b>\n\nСтратегии, книги и новости.", reply_markup=learning_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_activities")
async def menu_activities(callback: CallbackQuery):
    await safe_edit(callback.message, "🎮 <b>АКТИВНОСТИ</b>\n\nБонусы, магазин и рефералы.", reply_markup=activities_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    await safe_edit(callback.message, "💎 <b>ПРОФИЛЬ</b>\n\nПодписка, настройки и помощь.", reply_markup=profile_menu_kb())
    await callback.answer()