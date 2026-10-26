import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.crypto import encrypt
from services.exchange import test_keys
from database import add_exchange_key, list_exchange_keys, delete_exchange_key

logger = logging.getLogger(__name__)
router = Router()


class KeyStates(StatesGroup):
    waiting_api_key = State()
    waiting_secret = State()


async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else:
                await msg.answer(text, parse_mode=parse_mode)
        except Exception:
            pass


def exchanges_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Binance", callback_data="exch_binance")],
        [InlineKeyboardButton(text="Bybit", callback_data="exch_bybit")],
        [InlineKeyboardButton(text="Назад", callback_data="keys_menu")],
    ])


def modes_kb(exchange):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Testnet (demo)", callback_data=f"mode_{exchange}_testnet")],
        [InlineKeyboardButton(text="Mainnet (real)", callback_data=f"mode_{exchange}_mainnet")],
        [InlineKeyboardButton(text="Назад", callback_data="keys_add")],
    ])


def markets_kb(exchange, mode):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Spot", callback_data=f"market_{exchange}_{mode}_spot")],
        [InlineKeyboardButton(text="Futures", callback_data=f"market_{exchange}_{mode}_futures")],
        [InlineKeyboardButton(text="Назад", callback_data="keys_add")],
    ])


def keys_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ключи", callback_data="keys_add")],
        [InlineKeyboardButton(text="⚠️ Реальная торговля", callback_data="keys_agree_real")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "keys_menu")
async def keys_menu(callback: CallbackQuery):
    keys = await list_exchange_keys(callback.from_user.id)
    text = "🔑 <b>API-КЛЮЧИ</b>\n\nТвои подключённые биржи.\nКлючи шифруются AES-256.\n\n"
    if not keys:
        text += "Пока пусто. Добавь ключи чтобы торговать."
    else:
        for k in keys:
            mode_ru = "testnet" if k["mode"] == "testnet" else "mainnet"
            text += f"• {k['exchange'].capitalize()} / {mode_ru} / {k['market']}\n"
    await safe_edit(callback.message, text, reply_markup=keys_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "keys_add")
async def keys_add(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback.message, "Выбери биржу:", reply_markup=exchanges_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("exch_"))
async def choose_exchange(callback: CallbackQuery, state: FSMContext):
    exchange = callback.data.replace("exch_", "")
    await state.update_data(exchange=exchange)
    await safe_edit(callback.message, f"Биржа: {exchange.capitalize()}\n\nВыбери режим:", reply_markup=modes_kb(exchange))
    await callback.answer()


@router.callback_query(F.data.startswith("mode_"))
async def choose_mode(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.replace("mode_", "").split("_")
    exchange = parts[0]
    mode = parts[1]
    await state.update_data(mode=mode)
    await safe_edit(callback.message, f"Режим: {mode}\n\nВыбери рынок:", reply_markup=markets_kb(exchange, mode))
    await callback.answer()


@router.callback_query(F.data.startswith("market_"))
async def choose_market(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.replace("market_", "").split("_")
    exchange = parts[0]
    mode = parts[1]
    market = parts[2]
    await state.update_data(market=market)
    await safe_edit(
        callback.message,
        f"Биржа: {exchange}\nРежим: {mode}\nРынок: {market}\n\n"
        f"Отправь API KEY (сообщение будет удалено сразу):"
    )
    await state.set_state(KeyStates.waiting_api_key)
    await callback.answer()


@router.message(KeyStates.waiting_api_key)
async def receive_api_key(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(api_key=message.text.strip())
    await message.answer("API KEY получен.\nТеперь отправь SECRET (тоже удалю):")
    await state.set_state(KeyStates.waiting_secret)


@router.message(KeyStates.waiting_secret)
async def receive_secret(message: Message, state: FSMContext):
    try:
        await message.delete()
    except Exception:
        pass
    secret = message.text.strip()
    data = await state.get_data()
    exchange = data.get("exchange")
    mode = data.get("mode")
    market = data.get("market")
    api_key = data.get("api_key")

    await add_exchange_key(
        user_id=message.from_user.id,
        exchange=exchange,
        mode=mode,
        market=market,
        api_key_enc=encrypt(api_key),
        secret_enc=encrypt(secret),
    )

    test = await test_keys(message.from_user.id, exchange, mode, market)
    if test.get("ok"):
        bal = test.get("balance", {})
        usdt = bal.get("USDT", 0)
        await message.answer(
            f"✅ Ключи сохранены и работают.\n\n"
            f"Биржа: {exchange}\n"
            f"Режим: {mode}\n"
            f"Рынок: {market}\n"
            f"Баланс USDT: {usdt}"
        )
    else:
        await message.answer(
            f"⚠️ Ключи сохранены, но проверка не прошла:\n{test.get('error')}\n\n"
            f"Проверь права ключа (Trade + Read)."
        )

    await state.clear()

from services.pdf_agreement import create_agreement_pdf
from aiogram.types import FSInputFile
import os

@router.callback_query(F.data == "keys_agree_real")
async def keys_agree_real(callback: CallbackQuery):
    await callback.message.answer("⏳ Генерирую PDF-соглашение...")
    
    path = create_agreement_pdf(
        callback.from_user.id,
        callback.from_user.username or "",
        callback.from_user.first_name or ""
    )
    
    if os.path.exists(path):
        doc = FSInputFile(path)
        await callback.message.answer_document(
            doc,
            caption=(
                "📄 <b>Соглашение о рисках</b>\n\n"
                "Этот документ подтверждает, что вы понимаете риски реальной торговли.\n\n"
                "Он нужен для вашей же защиты.\n\n"
                "Нажмите кнопку ниже, чтобы подтвердить, что вы прочитали и согласны."
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Я прочитал и согласен", callback_data="keys_agree_confirm")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="keys_menu")]
            ]),
            parse_mode="HTML"
        )
        try: os.remove(path)
        except: pass
    else:
        await callback.message.answer("❌ Ошибка генерации PDF.")
    await callback.answer()


@router.callback_query(F.data == "keys_agree_confirm")
async def keys_agree_confirm(callback: CallbackQuery):
    # Убираем кнопки у документа (если возможно)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    # Отправляем новое сообщение с текстом
    await callback.message.answer(
        "✅ <b>Согласие принято!</b>\n\n"
        "Теперь вы можете добавить ключи Mainnet для реальной торговли.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Добавить ключи Mainnet", callback_data="keys_add")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="keys_menu")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer("Согласие принято")
