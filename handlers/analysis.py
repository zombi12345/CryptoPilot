import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import AnalysisStates
from keyboards.main import main_menu_keyboard
from services.vision import analyze_photo, format_forecast
from services.chart_generator import generate_chart_image
from database import check_and_increment_ai
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()

_last_results = {}

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception: pass

def result_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Подробнее", callback_data="analysis_details")],
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]
    ])

@router.callback_query(F.data == "stub_analysis")
async def analysis_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    can_use, current, limit = await check_and_increment_ai(callback.from_user.id)
    if not can_use:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 Купить подписку", callback_data="sub_menu")], [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")]])
        return await safe_edit(callback.message, f"🚫 <b>Лимит AI исчерпан</b>\n\nВы использовали {current} из {limit} запросов на сегодня.\n\nКупите подписку Premium или обратитесь к администратору.", reply_markup=kb)
        
    await safe_edit(
        callback.message,
        f"📊 <b>АНАЛИЗ ГРАФИКОВ</b>\n\n"
        f"Использовано запросов: {current}/{limit}\n\n"
        "Отправь скриншот графика. Я распознаю тикер, тренд, индикаторы и дам прогноз.\n\n"
        "👇 Отправь фото или /cancel",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS)
    )
    await state.set_state(AnalysisStates.waiting_photo)
    await callback.answer()

@router.message(AnalysisStates.waiting_photo, F.photo)
async def handle_photo(message: Message, state: FSMContext):
    msg = await message.answer("⏳ Анализирую фото графика...")
    
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    file_bytes = await message.bot.download_file(file.file_path)
    
    result = await analyze_photo(file_bytes.read(), user_id=message.from_user.id)
    
    if result.get("error"):
        await safe_edit(msg, f"❌ Ошибка: {result['error']}")
        return

    ticker = result.get("ticker")
    timeframe = result.get("timeframe", "1h")
    
    if ticker:
        await safe_edit(msg, "📈 Строю график по реальным данным...")
        symbol = ticker.replace("/", "")
        try:
            chart_buf = await generate_chart_image(symbol, timeframe)
            if chart_buf:
                photo_file = BufferedInputFile(chart_buf.read(), filename="chart.png")
                await message.answer_photo(photo_file, caption=f"📈 <b>График {ticker} ({timeframe})</b>", parse_mode="HTML")
        except Exception as e:
            logger.warning(f"График не сгенерирован: {e}")

    _last_results[message.from_user.id] = result
    text = format_forecast(result)
    if len(text) > 4000: text = text[:4000] + "\n(обрезано)"
    await safe_edit(msg, text, reply_markup=result_kb())
    await state.clear()

@router.callback_query(F.data == "analysis_details")
async def analysis_details(callback: CallbackQuery):
    user_id = callback.from_user.id
    result = _last_results.get(user_id)
    if not result:
        await callback.answer("Нет данных. Сначала отправь график.", show_alert=True)
        return
    from services.vision import format_details
    text = format_details(result)
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for p in parts:
            try: await callback.message.answer(p, parse_mode="HTML")
            except Exception: pass
        await callback.answer()
        return
    try: await callback.message.answer(text, parse_mode="HTML")
    except Exception: pass
    await callback.answer()

@router.message(AnalysisStates.waiting_photo)
async def need_photo(message: Message):
    await message.answer("Отправь фото графика или /cancel")