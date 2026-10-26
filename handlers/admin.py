import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import AdminStates
from database import get_pool, get_all_global_settings, set_global_setting, unban_all, ban_all_non_admins
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id):
    return user_id in ADMINS


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


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Глобальные дефолты", callback_data="admin_global")],
        [InlineKeyboardButton(text="📜 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="✅ Разбанить всех", callback_data="admin_unban_all")],
        [InlineKeyboardButton(text="🚨 EMERGENCY STOP", callback_data="admin_stop")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


def user_kb(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Лимиты", callback_data=f"admin_limits_{user_id}")],
        [InlineKeyboardButton(text="Забанить/Разбанить", callback_data=f"admin_ban_{user_id}")],
        [InlineKeyboardButton(text="Админ-права", callback_data=f"admin_promote_{user_id}")],
        [InlineKeyboardButton(text="Стратегии юзера", callback_data=f"admin_user_strats_{user_id}")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_users")],
    ])


def global_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Плечо", callback_data="gset_default_max_leverage")],
        [InlineKeyboardButton(text="Риск %", callback_data="gset_default_max_risk_pct")],
        [InlineKeyboardButton(text="Депозит $", callback_data="gset_default_deposit_limit")],
        [InlineKeyboardButton(text="Убыток %/день", callback_data="gset_default_daily_loss_limit_pct")],
        [InlineKeyboardButton(text="Сделок/день", callback_data="gset_default_daily_trades_limit")],
        [InlineKeyboardButton(text="Спот вкл/выкл", callback_data="gset_default_allow_spot")],
        [InlineKeyboardButton(text="Фьючерсы вкл/выкл", callback_data="gset_default_allow_futures")],
        [InlineKeyboardButton(text="Назад", callback_data="stub_admin")],
    ])


@router.callback_query(F.data == "stub_admin")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
        strats = await conn.fetchval("SELECT COUNT(*) FROM strategies")
        bts = await conn.fetchval("SELECT COUNT(*) FROM backtests")
        books = await conn.fetchval("SELECT COUNT(DISTINCT filename) FROM book_summaries")
    text = (
        "АДМИН-ПАНЕЛЬ\n\n"
        f"Пользователей: {users_count or 0}\n"
        f"Забанено: {banned or 0}\n"
        f"Стратегий: {strats or 0}\n"
        f"Бэктестов: {bts or 0}\n"
        f"Книг: {books or 0}\n\n"
        "Выбери раздел:"
    )
    await safe_edit(callback.message, text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        agreed = await conn.fetchval("SELECT COUNT(*) FROM users WHERE agreed_at IS NOT NULL")
        admins = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_admin = TRUE")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
        strats = await conn.fetchval("SELECT COUNT(*) FROM strategies")
        active_strats = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE is_active = TRUE")
        bts = await conn.fetchval("SELECT COUNT(*) FROM backtests")
        avg_return = await conn.fetchval("SELECT AVG(total_return_pct) FROM backtests")
        top = await conn.fetch("SELECT s.user_id, u.first_name, COUNT(*) as cnt FROM strategies s LEFT JOIN users u ON u.user_id = s.user_id GROUP BY s.user_id, u.first_name ORDER BY cnt DESC LIMIT 5")
    text = (
        "СТАТИСТИКА\n\n"
        f"Пользователей: {users_count or 0}\n"
        f"Соглашение: {agreed or 0}\n"
        f"Админов: {admins or 0}\n"
        f"Забанено: {banned or 0}\n\n"
        f"Стратегий: {strats or 0} (активных: {active_strats or 0})\n"
        f"Бэктестов: {bts or 0}\n"
        f"Средняя доходность: {round(float(avg_return), 2) if avg_return else 0}%\n\n"
        "ТОП-5 по стратегиям:\n"
    )
    for r in top:
        text += f"  {r['first_name'] or r['user_id']}: {r['cnt']}\n"
    await safe_edit(callback.message, text, reply_markup=admin_kb())
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
        await safe_edit(callback.message, "Пользователей нет.", reply_markup=admin_kb())
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
    await safe_edit(callback.message, f"Пользователи: {len(rows)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_") & ~F.data.startswith("admin_user_strats_"))
async def admin_user_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_user_", ""))
    await _show_user(callback, uid)


async def _show_user(callback: CallbackQuery, uid: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", uid)
        strats = await conn.fetchval("SELECT COUNT(*) FROM strategies WHERE user_id = $1", uid)
        bts = await conn.fetchval("SELECT COUNT(*) FROM backtests WHERE user_id = $1", uid)
        books = await conn.fetchval("SELECT COUNT(DISTINCT filename) FROM book_summaries WHERE user_id = $1", uid)
    if not row:
        await callback.answer("Не найден", show_alert=True)
        return
    text = (
        f"ПОЛЬЗОВАТЕЛЬ\n\n"
        f"ID: {row['user_id']}\n"
        f"Имя: {row['first_name'] or '-'}\n"
        f"Username: @{row['username'] or '-'}\n"
        f"Админ: {'да' if row['is_admin'] else 'нет'}\n"
        f"Забанен: {'да' if row['is_banned'] else 'нет'}\n"
        f"Соглашение: {'да' if row['agreed_at'] else 'нет'}\n\n"
        f"ЛИМИТЫ:\n"
        f"  Плечо: {row['max_leverage']}x\n"
        f"  Риск: {row['max_risk_pct']}%\n"
        f"  Депозит: ${row['deposit_limit']}\n"
        f"  Убыток/день: {row['daily_loss_limit_pct']}%\n"
        f"  Сделок/день: {row['daily_trades_limit']}\n"
        f"  Спот: {'да' if row['allow_spot'] else 'нет'}\n"
        f"  Фьючерсы: {'да' if row['allow_futures'] else 'нет'}\n\n"
        f"АКТИВНОСТЬ:\n"
        f"  Стратегий: {strats or 0}\n"
        f"  Бэктестов: {bts or 0}\n"
        f"  Книг: {books or 0}"
    )
    await safe_edit(callback.message, text, reply_markup=user_kb(uid))
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
    await _show_user(callback, uid)


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
    await _show_user(callback, uid)


@router.callback_query(F.data.startswith("admin_limits_"))
async def admin_limits(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_limits_", ""))
    await state.update_data(target_uid=uid, gset_key=None)
    await safe_edit(callback.message, "Введи лимиты через пробел:\nmax_leverage max_risk_pct deposit_limit daily_loss_pct daily_trades\n\nПример: 3 2 100 3 10")
    await state.set_state(AdminStates.editing_limit)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_user_strats_"))
async def admin_user_strats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_user_strats_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, symbol, timeframe, is_active FROM strategies WHERE user_id = $1 ORDER BY created_at DESC", uid)
    if not rows:
        await safe_edit(callback.message, "У юзера нет стратегий.", reply_markup=user_kb(uid))
        await callback.answer()
        return
    text = f"СТРАТЕГИИ ЮЗЕРА {uid}:\n\n"
    for r in rows:
        status = "A" if r["is_active"] else "-"
        text += f"{status} #{r['id']} {r['name']} ({r['symbol']} {r['timeframe']})\n"
    await safe_edit(callback.message, text, reply_markup=user_kb(uid))
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await safe_edit(callback.message, "Введи текст рассылки всем пользователям:")
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.answer()


@router.message(AdminStates.waiting_broadcast, F.text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    text = message.text
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
    sent = 0
    failed = 0
    for r in rows:
        try:
            await message.bot.send_message(r["user_id"], f"📢 РАССЫЛКА\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    await state.clear()
    await message.answer(f"Отправлено: {sent}, ошибок: {failed}")


@router.callback_query(F.data == "admin_global")
async def admin_global(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    d = await get_all_global_settings()
    text = (
        "ГЛОБАЛЬНЫЕ ДЕФОЛТЫ\n\n"
        "Применяются к новым пользователям. Существующие не меняются.\n\n"
        f"Плечо: {d.get('default_max_leverage', 3)}x\n"
        f"Риск: {d.get('default_max_risk_pct', 2)}%\n"
        f"Депозит: ${d.get('default_deposit_limit', 100)}\n"
        f"Убыток/день: {d.get('default_daily_loss_limit_pct', 3)}%\n"
        f"Сделок/день: {d.get('default_daily_trades_limit', 10)}\n"
        f"Спот: {'да' if d.get('default_allow_spot', True) else 'нет'}\n"
        f"Фьючерсы: {'да' if d.get('default_allow_futures', False) else 'нет'}\n\n"
        "Нажми на параметр, чтобы изменить:"
    )
    await safe_edit(callback.message, text, reply_markup=global_kb())
    await callback.answer()


@router.callback_query(F.data.startswith("gset_"))
async def gset_value(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    key = callback.data.replace("gset_", "")
    if key in ("default_allow_spot", "default_allow_futures"):
        d = await get_all_global_settings()
        cur = d.get(key, False)
        await set_global_setting(key, not cur)
        await callback.answer("Изменено")
        await admin_global(callback)
        return
    await state.update_data(gset_key=key, target_uid=None)
    await safe_edit(callback.message, f"Введи новое значение для {key}:")
    await state.set_state(AdminStates.editing_limit)
    await callback.answer()


@router.message(AdminStates.editing_limit, F.text)
async def editing_limit_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    data = await state.get_data()
    key = data.get("gset_key")
    target_uid = data.get("target_uid")
    if key:
        try:
            if key in ("default_allow_spot", "default_allow_futures"):
                val = message.text.strip().lower() in ("1", "true", "да", "yes")
            elif key == "default_daily_trades_limit":
                val = int(message.text.strip())
            else:
                val = float(message.text.strip().replace(",", "."))
        except ValueError:
            await message.answer("Неверный формат.")
            return
        await set_global_setting(key, val)
        await state.clear()
        await message.answer(f"{key} = {val}")
        return
    if not target_uid:
        await message.answer("Ошибка контекста.")
        await state.clear()
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
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET max_leverage = $1, max_risk_pct = $2, deposit_limit = $3, daily_loss_limit_pct = $4, daily_trades_limit = $5 WHERE user_id = $6", lev, risk, dep, loss, trades, target_uid)
    await state.clear()
    await message.answer("Лимиты обновлены.")


@router.callback_query(F.data == "admin_logs")
async def admin_logs(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        recent_bts = await conn.fetch("SELECT user_id, symbol, timeframe, total_return_pct, max_drawdown_pct, win_rate, total_trades, created_at FROM backtests ORDER BY created_at DESC LIMIT 10")
    if not recent_bts:
        await safe_edit(callback.message, "Логов нет.", reply_markup=admin_kb())
        await callback.answer()
        return
    text = "ПОСЛЕДНИЕ БЭКТЕСТЫ:\n\n"
    for r in recent_bts:
        text += f"user={r['user_id']} {r['symbol']} {r['timeframe']}\n  return={r['total_return_pct']}% dd={r['max_drawdown_pct']}% wr={r['win_rate']}% trades={r['total_trades']}\n"
    await safe_edit(callback.message, text, reply_markup=admin_kb())
    await callback.answer()


@router.callback_query(F.data == "admin_unban_all")
async def admin_unban_all(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await unban_all()
    await safe_edit(callback.message, "✅ Все пользователи разбанены.", reply_markup=admin_kb())
    await callback.answer("Разбанено")


@router.callback_query(F.data == "admin_stop")
async def admin_stop(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await ban_all_non_admins()
    await safe_edit(callback.message, "🚨 EMERGENCY STOP\n\nВсе не-админы забанены. Торговля остановлена.", reply_markup=admin_kb())
    await callback.answer("STOP выполнен")
