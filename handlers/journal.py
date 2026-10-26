import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_pool

logger = logging.getLogger(__name__)
router = Router()

class JournalStates(StatesGroup):
    waiting_symbol = State()
    waiting_side = State()
    waiting_result = State()
    waiting_emotion = State()

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

@router.callback_query(F.data == "stub_journal")
async def journal_menu(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT COUNT(*) as total, 
                   COALESCE(SUM(result_usdt), 0) as total_pnl,
                   COUNT(*) FILTER (WHERE result_usdt > 0) as wins,
                   COUNT(*) FILTER (WHERE result_usdt <= 0) as losses
            FROM trader_journal WHERE user_id = $1
        """, callback.from_user.id)
        
    total = row["total"] or 0
    total_pnl = float(row["total_pnl"] or 0)
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    winrate = (wins / total * 100) if total > 0 else 0
    
    text = (
        "📔 <b>ДНЕВНИК ТРЕЙДЕРА</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        f"Всего сделок: <b>{total}</b>\n"
        f"✅ Прибыльных: {wins} | ❌ Убыточных: {losses}\n"
        f"🎯 Win rate: <b>{winrate:.1f}%</b>\n"
        f"💰 Общий PnL: <b>{'+' if total_pnl >= 0 else ''}{total_pnl:.2f} USDT</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "Записывай свои сделки и эмоции. Это поможет понять, как психология влияет на твою прибыль."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Записать сделку", callback_data="journal_add")],
        [InlineKeyboardButton(text="📜 Последние сделки", callback_data="journal_history")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "journal_add")
async def journal_add(callback: CallbackQuery, state: FSMContext):
    await safe_edit(callback.message, "Шаг 1/4: Введи тикер (например: BTCUSDT):")
    await state.set_state(JournalStates.waiting_symbol)
    await callback.answer()

@router.message(JournalStates.waiting_symbol, F.text)
async def process_symbol(message: Message, state: FSMContext):
    await state.update_data(symbol=message.text.strip().upper())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 LONG", callback_data="journal_side_buy")],
        [InlineKeyboardButton(text="🔴 SHORT", callback_data="journal_side_sell")]
    ])
    await message.answer("Шаг 2/4: Направление?", reply_markup=kb)
    await state.set_state(JournalStates.waiting_side)

@router.callback_query(JournalStates.waiting_side, F.data.startswith("journal_side_"))
async def process_side(callback: CallbackQuery, state: FSMContext):
    side = callback.data.replace("journal_side_", "")
    await state.update_data(side=side)
    await safe_edit(callback.message, "Шаг 3/4: Какой результат в USDT? (например: 50 или -20):")
    await state.set_state(JournalStates.waiting_result)
    await callback.answer()

@router.message(JournalStates.waiting_result, F.text)
async def process_result(message: Message, state: FSMContext):
    try:
        result = float(message.text.strip().replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число (например: 50.5 или -20)")
    await state.update_data(result=result)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😎 Уверенность", callback_data="emo_confident")],
        [InlineKeyboardButton(text="😨 Страх", callback_data="emo_fear")],
        [InlineKeyboardButton(text="🤑 Жадность", callback_data="emo_greed")],
        [InlineKeyboardButton(text="😐 Нейтрально", callback_data="emo_neutral")]
    ])
    await message.answer("Шаг 4/4: Какая была эмоция при входе?", reply_markup=kb)
    await state.set_state(JournalStates.waiting_emotion)

@router.callback_query(JournalStates.waiting_emotion, F.data.startswith("emo_"))
async def process_emotion(callback: CallbackQuery, state: FSMContext):
    emotion = callback.data.replace("emo_", "")
    data = await state.get_data()
    
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO trader_journal (user_id, symbol, side, result_usdt, emotion)
            VALUES ($1, $2, $3, $4, $5)
        """, callback.from_user.id, data['symbol'], data['side'], data['result'], emotion)
        
    await state.clear()
    await safe_edit(callback.message, "✅ Сделка успешно записана в дневник!")
    await callback.answer()

@router.callback_query(F.data == "journal_history")
async def journal_history(callback: CallbackQuery):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM trader_journal WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10", callback.from_user.id)
        
    if not rows:
        return await safe_edit(callback.message, "📜 Дневник пуст. Добавь первую сделку!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_journal")]]))
        
    text = "📜 <b>ПОСЛЕДНИЕ 10 СДЕЛОК</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    emoji_map = {"confident": "😎", "fear": "😨", "greed": "🤑", "neutral": "😐"}
    
    for r in rows:
        icon = "🟢" if float(r['result_usdt']) >= 0 else "🔴"
        side = "LONG" if r['side'] == "buy" else "SHORT"
        emo = emoji_map.get(r['emotion'], "😐")
        dt = r['created_at'].strftime("%d.%m")
        text += f"{icon} {r['symbol']} {side} | <b>{r['result_usdt']:+.2f}</b> USDT {emo} ({dt})\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_journal")]])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()