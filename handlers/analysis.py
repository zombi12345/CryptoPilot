import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from states import AnalysisStates
from keyboards.main import main_menu_keyboard
from services.vision import analyze_photo, format_forecast
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "stub_analysis")
async def analysis_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Анализ графиков\n\n"
        "Отправь фото графика - AI распознает тикер, таймфрейм, тренд и даст прогноз.\n\n"
        "Если данных не хватит - задам уточняющие вопросы.\n\n"
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

    result = await analyze_photo(image_bytes)

    if result.get("enough_data") is False:
        await state.update_data(image_bytes=image_bytes)
        text = format_forecast(result)
        await msg.edit_text(text)
        await state.set_state(AnalysisStates.waiting_ticker)
        return

    text = format_forecast(result)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(обрезано)"
    await msg.edit_text(text)


@router.message(AnalysisStates.waiting_ticker, F.text)
async def handle_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    image_bytes = data.get("image_bytes")
    if not image_bytes:
        await message.answer("Сначала отправь фото графика.")
        await state.set_state(AnalysisStates.waiting_photo)
        return

    msg = await message.answer("Учитываю уточнение, формирую прогноз...")
    result = await analyze_photo(image_bytes, clarification=message.text)

    text = format_forecast(result)
    if len(text) > 4000:
        text = text[:4000] + "\n\n(обрезано)"
    await msg.edit_text(text)
    await state.clear()


@router.message(AnalysisStates.waiting_photo)
async def need_photo(message: Message):
    await message.answer("Отправь фото графика или /cancel")