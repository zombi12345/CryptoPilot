import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import AnalysisStates
from keyboards.main import main_menu_keyboard
from services.vision import analyze_photo, format_forecast, format_details
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()

_last_results = {}


async def safe_edit(msg, text, reply_markup=None):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup)
        else:
            await msg.edit_text(text)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup)
            else:
                await msg.answer(text)
        except Exception:
            pass


def result_kb(has_details: bool):
    kb = []
    if has_details:
        kb.append([InlineKeyboardButton(text="📖 Подробнее", callback_data="analysis_details")])
    kb.append([InlineKeyboardButton(text="Меню", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.callback_query(F.data == "stub_analysis")
async def analysis_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(
        callback.message,
        "Анализ графиков\n\n"
        "Отправь фото графика - AI распознает тикер, таймфрейм, тренд, паттерны и даст прогноз.\n\n"
        "Если загружены книги в Библиотеке - AI учтёт их при анализе.\n\n"
        "Отправь фото или /cancel для отмены.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await state.set_state(AnalysisStates.waiting_photo)
    await callback.answer()


@router.message(AnalysisStates.waiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    msg = await message.answer("Анализирую график, подожди...")

    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    image_bytes = file_bytes.read()

    result = await analyze_photo(image_bytes, user_id=message.from_user.id)

    if result.get("enough_data") is False:
        await state.update_data(image_bytes=image_bytes)
        text = format_forecast(result)
        await safe_edit(msg, text)
        await state.set_state(AnalysisStates.waiting_ticker)
        return

    _last_results[message.from_user.id] = result
    text = format_forecast(result)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(обрезано)"
    await safe_edit(msg, text, reply_markup=result_kb(bool(result.get("forecast"))))


@router.callback_query(F.data == "analysis_details")
async def analysis_details(callback: CallbackQuery):
    user_id = callback.from_user.id
    result = _last_results.get(user_id)
    if not result:
        await callback.answer("Нет данных", show_alert=True)
        return
    text = format_details(result)
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for p in parts:
            try:
                await callback.message.answer(p)
            except Exception:
                pass
        await callback.answer()
        return
    try:
        await callback.message.answer(text, reply_markup=result_kb(False))
    except Exception:
        pass
    await callback.answer()


@router.message(AnalysisStates.waiting_ticker, F.text)
async def handle_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    image_bytes = data.get("image_bytes")
    if not image_bytes:
        await message.answer("Сначала отправь фото графика.")
        await state.set_state(AnalysisStates.waiting_photo)
        return

    msg = await message.answer("Учитываю уточнение и книги, формирую прогноз...")
    result = await analyze_photo(image_bytes, clarification=message.text, user_id=message.from_user.id)

    _last_results[message.from_user.id] = result
    text = format_forecast(result)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(обрезано)"
    await safe_edit(msg, text, reply_markup=result_kb(bool(result.get("forecast"))))
    await state.clear()


@router.message(AnalysisStates.waiting_photo)
async def need_photo(message: Message):
    await message.answer("Отправь фото графика или /cancel")