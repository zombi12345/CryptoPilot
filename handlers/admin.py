import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import AdminStates
from keyboards.main import main_menu_keyboard
from database import get_pool
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id):
    return user_id in ADMINS


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="🚨 EMERGENCY STOP", callback_data="admin_stop")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


def user_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Лимиты", callback_data=f"admin_limits_{user_id}")],
        [InlineKeyboardButton(text="Забанить/Разбанить", callback_data=f"admin_ban_{user_id}")],
        [InlineKeyboardButton(text="Админ-права", callback_data=f"admin_promote_{user_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_users")],
    ])


@router.callback_query(F.data == "stub_admin")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Админ-панель\n\nУправление ботом.",
        reply_markup=admin_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, first_name, is_admin, is_banned, deposit_limit FROM users ORDER BY created_at DESC LIMIT 30")
    if not rows:
        await callback.message.edit_text("Пользователей нет.", reply_markup=admin_kb())
        await callback.answer()
        return

    kb = []
    for r in rows:
        flag = "A" if r["is_admin"] else "U"
        ban = " [BAN]" if r["is_banned"] else ""
        name = r["first_name"] or r["username"] or str(r["user_id"])
        kb.append([InlineKeyboardButton(
            text=f"{flag} {name} (${r['deposit_limit']}){ban}",
            callback_data=f"admin_user_{r['user_id']}",
        )])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="stub_admin")])
    await callback.message.edit_text(
        f"Пользователи: {len(rows)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_"))
async def admin_user_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_user_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", uid)
    if not row:
        await callback.answer("Не найден", show_alert=True)
        return

    text = (
        f"Пользователь\n\n"
        f"ID: {row['user_id']}\n"
        f"Имя: {row['first_name'] or '-'}\n"
        f"Username: @{row['username'] or '-'}\n"
        f"Админ: {'да' if row['is_admin'] else 'нет'}\n"
        f"Забанен: {'да' if row['is_banned'] else 'нет'}\n"
        f"Соглашение: {'да' if row['agreed_at'] else 'нет'}\n\n"
        f"Макс плечо: {row['max_leverage']}x\n"
        f"Макс риск: {row['max_risk_pct']}%\n"
        f"Лимит депозита: ${row['deposit_limit']}\n"
        f"Дневной лимит убытка: {row['daily_loss_limit_pct']}%\n"
        f"Лимит сделок/день: {row['daily_trades_limit']}\n"
        f"Спот: {'да' if row['allow_spot'] else 'нет'}\n"
        f"Фьючерсы: {'да' if row['allow_futures'] else 'нет'}"
    )
    await callback.message.edit_text(text, reply_markup=user_kb(uid))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_ban_"))
async def admin_ban(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_ban_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", uid)
        new_val = not row["is_banned"]
        await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", new_val, uid)
    await callback.answer("Забанен" if new_val else "Разбанен")
    await admin_user_view(callback)


@router.callback_query(F.data.startswith("admin_promote_"))
async def admin_promote(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_promote_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_admin FROM users WHERE user_id = $1", uid)
        new_val = not row["is_admin"]
        await conn.execute("UPDATE users SET is_admin = $1 WHERE user_id = $2", new_val, uid)
    await callback.answer("Админ" if new_val else "Не админ")
    await admin_user_view(callback)


@router.callback_query(F.data.startswith("admin_limits_"))
async def admin_limits(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_limits_", ""))
    await state.update_data(target_uid=uid)
    await callback.message.edit_text(
        "Введи лимиты через пробел:\n"
        "max_leverage max_risk_pct deposit_limit daily_loss_pct daily_trades\n\n"
        "Пример: 3 2 100 3 10"
    )
    await state.set_state(AdminStates.editing_limit)
    await callback.answer()


@router.message(AdminStates.editing_limit, F.text)
async def admin_limits_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 5:
        await message.answer("Нужно 5 чисел.")
        return
    try:
        lev, risk, dep, loss, trades = map(float, parts)
        trades = int(trades)
    except ValueError:
        await message.answer("Неверный формат.")
        return

    data = await state.get_data()
    uid = data.get("target_uid")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET max_leverage = $1, max_risk_pct = $2, deposit_limit = $3,
                daily_loss_limit_pct = $4, daily_trades_limit = $5
            WHERE user_id = $6
        """, lev, risk, dep, loss, trades, uid)

    await state.clear()
    await message.answer("Лимиты обновлены.")


@router.callback_query(F.data == "admin_stop")
async def admin_stop(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = TRUE WHERE is_admin = FALSE")
    await callback.message.edit_text("🚨 EMERGENCY STOP: все не-админы забанены.", reply_markup=admin_kb())
    await callback.answer()