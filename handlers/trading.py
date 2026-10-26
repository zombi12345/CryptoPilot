import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import TradeStates
from services.risk_guard import check_trade
from services.exchange import place_order, fetch_positions, close_position, fetch_balance_full, transfer_spot_to_futures
from database import get_pool, get_user, list_exchange_keys, save_order, close_order_in_db, list_orders, get_orders_stats

logger = logging.getLogger(__name__)
router = Router()
_pending = {}

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e): return

@router.callback_query(F.data == "stub_trading")
async def trading_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    is_paid = user.get("is_paid", False) if user else False
    
    text = "💼 <b>ТОРГОВЛЯ</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    if not is_paid:
        text += "⚠️ <b>Доступен только Demo (Testnet)</b>\n<i>Для перехода на реал нужна подписка Premium.</i>\n\n"
    else:
        text += "Режим: <b>Demo (Testnet)</b>\n<i>Переход на реал — через админа.</i>\n\n"
        
    kb = [
        [InlineKeyboardButton(text="💰 Баланс", callback_data="trade_balance")],
        [InlineKeyboardButton(text="📊 Позиции", callback_data="trade_positions")],
        [InlineKeyboardButton(text="📈 Открыть сделку", callback_data="trade_open")],
        [InlineKeyboardButton(text="📜 История", callback_data="trade_history")],
        [InlineKeyboardButton(text="🤖 Автоторговля", callback_data="trade_auto")],
        [InlineKeyboardButton(text="🔑 API-ключи", callback_data="keys_menu")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
    ]
    await safe_edit(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

# ... остальные функции (баланс, позиции, история, автоторговля, открытие сделки) остаются без изменений.