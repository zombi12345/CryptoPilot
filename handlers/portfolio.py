import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_pool
from services.market_data import fetch_ohlcv

logger = logging.getLogger(__name__)
router = Router()

class PortfolioStates(StatesGroup):
    waiting_coin = State()
    waiting_amount = State()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

async def get_prices(coins):
    """Получает текущие цены для списка монет."""
    prices = {}
    for coin in coins:
        try:
            symbol = f"{coin}/USDT"
            df = await fetch_ohlcv(symbol, "1h", limit=1)
            if not df.empty:
                prices[coin] = float(df.iloc[-1]["close"])
        except Exception:
            pass
    return prices

@router.callback_query(F.data == "stub_portfolio")
async def portfolio_menu(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT coin, amount FROM portfolio WHERE user_id = $1", callback.from_user.id)
    
    if not rows:
        text = "💼 <b>МОЙ ПОРТФЕЛЬ</b>\n\nПортфель пуст. Добавь свои монеты, и я буду считать их стоимость в реальном времени."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить монету", callback_data="portfolio_add")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]
        ])
        return await safe_edit(callback.message, text, reply_markup=kb)
        
    coins = [r["coin"] for r in rows]
    prices = await get_prices(coins)
    
    text = "💼 <b>МОЙ ПОРТФЕЛЬ</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    total_usdt = 0
    
    for r in rows:
        coin = r["coin"]
        amount = float(r["amount"])
        price = prices.get(coin, 0)
        value = amount * price
        total_usdt += value
        text += f"• <b>{coin}</b>: {amount} (≈ ${value:.2f})\n"
        
    text += f"➖➖➖➖➖➖➖➖➖➖\n💰 <b>Всего: ${total_usdt:.2f} USDT</b>"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="portfolio_add")],
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="portfolio_clear")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stub_portfolio")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "portfolio_add")
async def portfolio_add(callback: CallbackQuery, state: FSMContext):
    await safe_edit(callback.message, "Введи тикер монеты (например: BTC):")
    await state.set_state(PortfolioStates.waiting_coin)
    await callback.answer()

@router.message(PortfolioStates.waiting_coin, F.text)
async def process_coin(message: Message, state: FSMContext):
    coin = message.text.strip().upper()
    await state.update_data(coin=coin)
    await message.answer(f"Сколько у тебя {coin}? (например: 0.5)")
    await state.set_state(PortfolioStates.waiting_amount)

@router.message(PortfolioStates.waiting_amount, F.text)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число (например: 0.5)")
        
    data = await state.get_data()
    coin = data['coin']
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO portfolio (user_id, coin, amount)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, coin) DO UPDATE SET amount = $3
        """, message.from_user.id, coin, amount)
        
    await state.clear()
    await message.answer(f"✅ Добавлено: {amount} {coin}")
    # Перенаправляем в меню портфеля (имитация нажатия)
    class FakeCallback:
        def __init__(self, msg, user): self.message = msg; self.from_user = user
        async def answer(self, *args, **kwargs): pass
    await portfolio_menu(FakeCallback(message, message.from_user))

@router.callback_query(F.data == "portfolio_clear")
async def portfolio_clear(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM portfolio WHERE user_id = $1", callback.from_user.id)
    await callback.answer("✅ Портфель очищен", show_alert=True)
    await portfolio_menu(callback)