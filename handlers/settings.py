import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from keyboards.main import main_menu_keyboard
from database import get_user, get_pool

logger = logging.getLogger(__name__)
router = Router()


def settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мой профиль", callback_data="settings_profile")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_settings")
async def settings_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Настройки\n\nУправление профилем и лимитами.",
        reply_markup=settings_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "settings_profile")
async def settings_profile(callback: CallbackQuery):
    uid = callback.from_user.id
    user = await get_user(uid)
    if not user:
        await callback.answer("Не найден", show_alert=True)
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        trades_count = await conn.fetchval("SELECT COUNT(*) FROM backtests WHERE user_id = $1", uid)
        strategies_count = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE user_id = $1", uid)

    text = (
        f"Мой профиль\n\n"
        f"ID: {uid}\n"
        f"Имя: {user.get('first_name') or '-'}\n"
        f"Соглашение: {'да' if user.get('agreed_at') else 'нет'}\n\n"
        f"Лимиты:\n"
        f"  Плечо: {user.get('max_leverage')}x\n"
        f"  Риск: {user.get('max_risk_pct')}%\n"
        f"  Депозит: ${user.get('deposit_limit')}\n"
        f"  Убыток/день: {user.get('daily_loss_limit_pct')}%\n"
        f"  Сделок/день: {user.get('daily_trades_limit')}\n\n"
        f"Стратегий: {strategies_count or 0}\n"
        f"Бэктестов: {trades_count or 0}\n\n"
        f"Лимиты меняет админ."
    )
    await callback.message.edit_text(text, reply_markup=settings_kb())
    await callback.answer()