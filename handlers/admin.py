import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import get_pool, get_user, unban_all, ban_all_non_admins
from handlers.ads_display import get_ads_config, set_ads_config
from config import ADMINS

logger = logging.getLogger(__name__)
router = Router()

class AdminStates(StatesGroup):
    waiting_broadcast = State()
    waiting_days = State()
    waiting_user_id = State()
    waiting_price = State()
    waiting_ad_text = State()
    waiting_ad_link = State()
    waiting_ad_button = State()
    waiting_admin_id = State()
    waiting_trial_days = State()
    waiting_edit_text = State()
    waiting_edit_link = State()
    waiting_edit_btn = State()
    waiting_shop_title = State()
    waiting_shop_desc = State()
    waiting_shop_price = State()
    waiting_shop_value = State()
    waiting_bonus_coins = State()

def _is_admin(user_id):
    return user_id in ADMINS

async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup: await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else: await msg.edit_text(text, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" in str(e): return
        try:
            if reply_markup: await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            else: await msg.answer(text, parse_mode=parse_mode)
        except Exception: pass

async def get_setting(key, default):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM global_settings WHERE key = $1", key)
    if not row: return default
    return str(row["value"]).replace('"', '')

async def set_setting(key, value):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO global_settings (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = $2::jsonb", key, f'"{value}"')

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"), InlineKeyboardButton(text="👥 Юзеры", callback_data="admin_users")],
        [InlineKeyboardButton(text="💎 Подписки", callback_data="admin_subs_menu"), InlineKeyboardButton(text="🎁 Триал", callback_data="admin_trial")],
        [InlineKeyboardButton(text="📢 Реклама", callback_data="admin_ads"), InlineKeyboardButton(text="🛒 Магазин", callback_data="admin_shop")],
        [InlineKeyboardButton(text="🎁 Бонусы", callback_data="admin_bonus_settings"), InlineKeyboardButton(text="👑 Админы", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🚨 EMERGENCY STOP", callback_data="admin_stop")],
        [InlineKeyboardButton(text="⬅️ Выход", callback_data="back_to_menu")],
    ])

def user_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Выдать подписку", callback_data=f"admin_sub_{uid}")],
        [InlineKeyboardButton(text="🎁 Сбросить триал", callback_data=f"admin_reset_trial_{uid}")],
        [InlineKeyboardButton(text="🚫 Забанить/Разбанить", callback_data=f"admin_ban_{uid}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_users")],
    ])

def pricing_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ 1 месяц", callback_data="admin_edit_1m")],
        [InlineKeyboardButton(text="✏️ 3 месяца", callback_data="admin_edit_3m")],
        [InlineKeyboardButton(text="✏️ 1 год", callback_data="admin_edit_1y")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_subs_menu")],
    ])

def ads_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="admin_ad_add")], 
        [InlineKeyboardButton(text="📋 Список", callback_data="admin_ad_list")], 
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_ad_settings")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")]
    ])

def ad_edit_kb(ad_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить текст", callback_data=f"admin_edit_text_{ad_id}")],
        [InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data=f"admin_edit_link_{ad_id}")],
        [InlineKeyboardButton(text="🔘 Изменить кнопку", callback_data=f"admin_edit_btn_{ad_id}")],
        [InlineKeyboardButton(text="✅ Вкл/Выкл", callback_data=f"admin_ad_toggle_{ad_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_ad_delete_{ad_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_ad_list")],
    ])

@router.callback_query(F.data == "stub_admin")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(callback.from_user.id): return await callback.answer("Нет доступа", show_alert=True)
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        paid = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_paid = TRUE")
        stars = await conn.fetchval("SELECT COALESCE(SUM(stars_paid), 0) FROM payments")
    text = f"👑 <b>АДМИН-ПАНЕЛЬ CryptoPilot</b>\n➖➖➖➖➖➖➖➖➖➖\n👥 Юзеров: <b>{total}</b>\n💎 Платных: <b>{paid}</b>\n⭐ Заработано: <b>{stars}</b>\n➖➖➖➖➖➖➖➖➖➖\nВыбери раздел для управления:"
    await safe_edit(callback.message, text, reply_markup=admin_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        paid = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_paid = TRUE")
        trial = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_used = TRUE")
        banned = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
        stars = await conn.fetchval("SELECT COALESCE(SUM(stars_paid), 0) FROM payments")
    text = f"📊 <b>ПОДРОБНАЯ СТАТИСТИКА</b>\n➖➖➖➖➖➖➖➖➖➖\n👥 Всего юзеров: <b>{total}</b>\n🆓 Бесплатных: <b>{total - paid}</b>\n💎 Платных: <b>{paid}</b>\n🎁 На триале: <b>{trial}</b>\n⛔️ Забанено: <b>{banned}</b>\n➖➖➖➖➖➖➖➖➖➖\n⭐ Всего заработано: <b>{stars} ⭐</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"), InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")]])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "admin_bonus_settings")
async def admin_bonus_settings(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    base = await get_setting("bonus_base", "10")
    step = await get_setting("bonus_step", "5")
    text = f"🎁 <b>НАСТРОЙКИ БОНУСОВ</b>\n\nБазовый бонус: {base}\nШаг стрика: {step}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить базовый бонус", callback_data="edit_bonus_base")],
        [InlineKeyboardButton(text="✏️ Изменить шаг стрика", callback_data="edit_bonus_step")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")],
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("edit_bonus_"))
async def edit_bonus_prompt(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    field = callback.data.replace("edit_bonus_", "")
    await state.update_data(bonus_field=field)
    await safe_edit(callback.message, f"Введи новое значение для {field}:")
    await state.set_state(AdminStates.waiting_bonus_coins)
    await callback.answer()

@router.message(AdminStates.waiting_bonus_coins, F.text)
async def edit_bonus_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: val = int(message.text.strip())
    except: return await message.answer("❌ Нужно число.")
    data = await state.get_data()
    field = data.get("bonus_field")
    await set_setting(f"bonus_{field}", str(val))
    await state.clear()
    await message.answer(f"✅ Обновлено: {field} = {val}")

@router.callback_query(F.data == "admin_shop")
async def admin_shop(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, title, price, is_active, item_type FROM shop_items")
    text = "🛒 <b>УПРАВЛЕНИЕ МАГАЗИНОМ</b>\n\n"
    kb = []
    for r in rows:
        icon = "✅" if r["is_active"] else "❌"
        kb.append([InlineKeyboardButton(text=f"{icon} {r['title']} ({r['price']})", callback_data=f"admin_shop_view_{r['id']}")])
    kb.append([InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_shop_add")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")])
    await safe_edit(callback.message, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data == "admin_shop_add")
async def admin_shop_add(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "Выбери тип товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст / Промокод", callback_data="shop_type_text")],
        [InlineKeyboardButton(text="💎 Подписка (дни)", callback_data="shop_type_sub")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_shop")]
    ]))
    await callback.answer()

@router.callback_query(F.data == "shop_type_text")
async def shop_type_text(callback: CallbackQuery, state: FSMContext):
    await state.update_data(item_type="text")
    await safe_edit(callback.message, "Шаг 1/4: Введи название товара:")
    await state.set_state(AdminStates.waiting_shop_title)
    await callback.answer()

@router.callback_query(F.data == "shop_type_sub")
async def shop_type_sub(callback: CallbackQuery, state: FSMContext):
    await state.update_data(item_type="sub")
    await safe_edit(callback.message, "Шаг 1/4: Введи название товара (например: Подписка на 7 дней):")
    await state.set_state(AdminStates.waiting_shop_title)
    await callback.answer()

@router.message(AdminStates.waiting_shop_title, F.text)
async def admin_shop_title(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    await state.update_data(title=message.text)
    await message.answer("Шаг 2/4: Введи описание (или 'нет'):")
    await state.set_state(AdminStates.waiting_shop_desc)

@router.message(AdminStates.waiting_shop_desc, F.text)
async def admin_shop_desc(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    desc = message.text.strip()
    if desc.lower() == "нет": desc = ""
    await state.update_data(desc=desc)
    await message.answer("Шаг 3/4: Введи цену в монетах:")
    await state.set_state(AdminStates.waiting_shop_price)

@router.message(AdminStates.waiting_shop_price, F.text)
async def admin_shop_price(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: price = int(message.text.strip())
    except: return await message.answer("❌ Нужно число.")
    await state.update_data(price=price)
    
    data = await state.get_data()
    if data.get("item_type") == "sub":
        await message.answer("Шаг 4/4: На сколько ДНЕЙ выдать подписку при покупке?")
    else:
        await message.answer("Шаг 4/4: Что выдать при покупке (текст или промокод):")
    await state.set_state(AdminStates.waiting_shop_value)

@router.message(AdminStates.waiting_shop_value, F.text)
async def admin_shop_value(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    data = await state.get_data()
    item_type = data.get("item_type", "text")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO shop_items (title, description, price, item_type, item_value) VALUES ($1, $2, $3, $4, $5)", data['title'], data['desc'], data['price'], item_type, message.text)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_shop")]])
    await message.answer("✅ Товар добавлен!", reply_markup=kb)

@router.callback_query(F.data.startswith("admin_shop_view_"))
async def admin_shop_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    item_id = int(callback.data.replace("admin_shop_view_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM shop_items WHERE id = $1", item_id)
    if not r: return await callback.answer("Нет такого", show_alert=True)
    
    type_str = "Подписка" if r['item_type'] == 'sub' else "Текст"
    text = f"🛒 <b>{r['title']}</b>\nЦена: {r['price']} монет\nТип: {type_str}\nВыдача: {r['item_value']}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выкл/Вкл", callback_data=f"admin_shop_toggle_{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_shop_del_{item_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_shop")],
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data.startswith("admin_shop_toggle_"))
async def admin_shop_toggle(callback: CallbackQuery):
    item_id = int(callback.data.replace("admin_shop_toggle_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE shop_items SET is_active = NOT is_active WHERE id = $1", item_id)
    await callback.answer("Изменено")
    await admin_shop(callback)

@router.callback_query(F.data.startswith("admin_shop_del_"))
async def admin_shop_del(callback: CallbackQuery):
    item_id = int(callback.data.replace("admin_shop_del_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM shop_items WHERE id = $1", item_id)
    await callback.answer("✅ Удалено", show_alert=True)
    await admin_shop(callback)

@router.callback_query(F.data == "admin_ads")
async def admin_ads(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM ads")
        shows = await conn.fetchval("SELECT COUNT(*) FROM ad_stats WHERE action = 'show'")
        clicks = await conn.fetchval("SELECT COUNT(*) FROM ad_stats WHERE action = 'click'")
    config = await get_ads_config()
    status = "🟢 Вкл" if config.get("enabled") else "🔴 Выкл"
    text = f"📢 <b>РЕКЛАМА</b>\n➖➖➖➖➖➖➖➖➖➖\nСтатус: {status}\nБлоков: <b>{count}</b>\nПоказов: <b>{shows}</b> | Кликов: <b>{clicks}</b>"
    await safe_edit(callback.message, text, reply_markup=ads_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_ad_settings")
async def admin_ad_settings(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    config = await get_ads_config()
    status = "🟢 Включена" if config.get("enabled") else "🔴 Выключена"
    freq = {"always": "Всегда", "daily": "Раз в день", "every_n": f"Каждый {config.get('frequency_value', 3)}-й раз"}.get(config.get("frequency"), "Раз в день")
    text = f"⚙️ <b>НАСТРОЙКИ РЕКЛАМЫ</b>\n➖➖➖➖➖➖➖➖➖➖\nСтатус: {status}\nЧастота: {freq}\nЛимит/день: {config.get('max_per_day')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выключить" if config.get("enabled") else "✅ Включить", callback_data="ads_toggle_all")],
        [InlineKeyboardButton(text="Раз в день", callback_data="set_freq_daily")],
        [InlineKeyboardButton(text="Всегда", callback_data="set_freq_always")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_ads")],
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "ads_toggle_all")
async def ads_toggle_all(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    config = await get_ads_config()
    await set_ads_config(enabled=not config.get("enabled"))
    await callback.answer("Статус изменен")
    await admin_ad_settings(callback)

@router.callback_query(F.data.startswith("set_freq_"))
async def set_freq(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    freq = callback.data.replace("set_freq_", "")
    await set_ads_config(frequency=freq)
    await callback.answer("Частота обновлена")
    await admin_ad_settings(callback)

@router.callback_query(F.data == "admin_ad_list")
async def admin_ad_list(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.id, a.text, a.enabled,
            (SELECT COUNT(*) FROM ad_stats WHERE ad_id = a.id AND action = 'show') as shows,
            (SELECT COUNT(*) FROM ad_stats WHERE ad_id = a.id AND action = 'click') as clicks
            FROM ads a
        """)
    if not rows: return await safe_edit(callback.message, "Пусто.", reply_markup=ads_kb())
    kb = []
    for r in rows:
        icon = "✅" if r["enabled"] else "❌"
        text_btn = f"{icon} {r['text'][:15]}... (👁 {r['shows']} | 👆 {r['clicks']})"
        kb.append([InlineKeyboardButton(text=text_btn, callback_data=f"admin_ad_view_{r['id']}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_ads")])
    await safe_edit(callback.message, "📋 <b>Список рекламы:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_ad_view_"))
async def admin_ad_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_ad_view_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
    if not r: return await callback.answer("Не найден", show_alert=True)
    
    text = f"📢 <b>Блок #{ad_id}</b>\n➖➖➖➖➖➖➖➖➖➖\n📝 Текст: {r['text']}\n🔗 Ссылка: {r['link'] or 'нет'}\n🔘 Кнопка: {r['button_text']}\nСтатус: {'✅' if r['enabled'] else '❌'}"
    await safe_edit(callback.message, text, reply_markup=ad_edit_kb(ad_id))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_ad_toggle_"))
async def admin_ad_toggle(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_ad_toggle_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ads SET enabled = NOT enabled WHERE id = $1", ad_id)
    await callback.answer("Изменено")
    await admin_ad_view(callback)

@router.callback_query(F.data.startswith("admin_ad_delete_"))
async def admin_ad_delete(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_ad_delete_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM ads WHERE id = $1", ad_id)
    await callback.answer("✅ Удалено", show_alert=True)
    await admin_ad_list(callback)

@router.callback_query(F.data == "admin_ad_add")
async def admin_ad_add(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "Шаг 1/3: Отправь текст рекламы:")
    await state.set_state(AdminStates.waiting_ad_text)
    await callback.answer()

@router.message(AdminStates.waiting_ad_text, F.text)
async def admin_ad_text(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    await state.update_data(ad_text=message.text)
    await message.answer("Шаг 2/3: Отправь ссылку (или 'нет'):")
    await state.set_state(AdminStates.waiting_ad_link)

@router.message(AdminStates.waiting_ad_link, F.text)
async def admin_ad_link(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    link = message.text.strip()
    if link.lower() == "нет": link = ""
    await state.update_data(ad_link=link)
    await message.answer("Шаг 3/3: Текст на кнопке:")
    await state.set_state(AdminStates.waiting_ad_button)

@router.message(AdminStates.waiting_ad_button, F.text)
async def admin_ad_button(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    data = await state.get_data()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO ads (text, link, button_text, enabled) VALUES ($1, $2, $3, TRUE)", data["ad_text"], data["ad_link"], message.text.strip())
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="stub_admin")]])
    await message.answer("✅ Реклама добавлена!", reply_markup=kb)

@router.callback_query(F.data.startswith("admin_edit_text_"))
async def ad_edit_text(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_edit_text_", ""))
    await state.update_data(ad_id=ad_id)
    await safe_edit(callback.message, "Введи НОВЫЙ текст рекламы:")
    await state.set_state(AdminStates.waiting_edit_text)
    await callback.answer()

@router.message(AdminStates.waiting_edit_text, F.text)
async def ad_edit_text_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    data = await state.get_data()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ads SET text = $1 WHERE id = $2", message.text, data['ad_id'])
    await state.clear()
    await message.answer("✅ Текст обновлен!")

@router.callback_query(F.data.startswith("admin_edit_link_"))
async def ad_edit_link(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_edit_link_", ""))
    await state.update_data(ad_id=ad_id)
    await safe_edit(callback.message, "Введи НОВУЮ ссылку (или 'нет'):")
    await state.set_state(AdminStates.waiting_edit_link)
    await callback.answer()

@router.message(AdminStates.waiting_edit_link, F.text)
async def ad_edit_link_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    link = message.text.strip()
    if link.lower() == "нет": link = ""
    data = await state.get_data()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ads SET link = $1 WHERE id = $2", link, data['ad_id'])
    await state.clear()
    await message.answer("✅ Ссылка обновлена!")

@router.callback_query(F.data.startswith("admin_edit_btn_"))
async def ad_edit_btn(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    ad_id = int(callback.data.replace("admin_edit_btn_", ""))
    await state.update_data(ad_id=ad_id)
    await safe_edit(callback.message, "Введи НОВЫЙ текст на кнопке:")
    await state.set_state(AdminStates.waiting_edit_btn)
    await callback.answer()

@router.message(AdminStates.waiting_edit_btn, F.text)
async def ad_edit_btn_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    data = await state.get_data()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE ads SET button_text = $1 WHERE id = $2", message.text, data['ad_id'])
    await state.clear()
    await message.answer("✅ Кнопка обновлена!")

@router.callback_query(F.data == "admin_subs_menu")
async def admin_subs_menu(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_paid = TRUE")
    text = f"💎 <b>УПРАВЛЕНИЕ ПОДПИСКАМИ</b>\n➖➖➖➖➖➖➖➖➖➖\nАктивных подписок: <b>{active}</b>"
    await safe_edit(callback.message, text, reply_markup=subs_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_pricing")
async def admin_pricing(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM global_settings WHERE key LIKE 'plan_%'")
    plans = {"1m": {"name": "1 месяц", "days": 30, "stars": 150}, "3m": {"name": "3 месяца", "days": 90, "stars": 400}, "1y": {"name": "1 год", "days": 365, "stars": 1500}}
    for r in rows:
        key = r["key"]
        val = str(r["value"]).replace('"', '')
        if "_stars" in key:
            pid = key.replace("plan_", "").replace("_stars", "")
            if pid in plans: 
                try: plans[pid]["stars"] = int(val)
                except: pass
        elif "_days" in key:
            pid = key.replace("plan_", "").replace("_days", "")
            if pid in plans: 
                try: plans[pid]["days"] = int(val)
                except: pass
    text = "💰 <b>ЦЕНЫ И ПЕРИОДЫ</b>\n➖➖➖➖➖➖➖➖➖➖\n"
    for pid, info in plans.items(): text += f"• {info['name']}: <b>{info['days']} дн.</b> — <b>{info['stars']} ⭐</b>\n"
    await safe_edit(callback.message, text, reply_markup=pricing_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("admin_edit_"))
async def admin_edit_price(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    plan_id = callback.data.replace("admin_edit_", "")
    await state.update_data(plan_id=plan_id)
    await safe_edit(callback.message, "Введи цену в звездах и срок в днях через пробел (например: <code>200 30</code>):")
    await state.set_state(AdminStates.waiting_price)
    await callback.answer()

@router.message(AdminStates.waiting_price, F.text)
async def admin_save_price(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) != 2: return await message.answer("❌ Нужно: Звезды Дни")
    try: stars, days = int(parts[0]), int(parts[1])
    except: return await message.answer("❌ Нужны числа.")
    data = await state.get_data()
    plan_id = data['plan_id']
    await set_setting(f"plan_{plan_id}_stars", str(stars))
    await set_setting(f"plan_{plan_id}_days", str(days))
    await state.clear()
    await message.answer(f"✅ Обновлено: {stars} ⭐ за {days} дней")

@router.callback_query(F.data == "admin_sub_give")
async def admin_sub_give(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "Введи ID юзера:")
    await state.set_state(AdminStates.waiting_user_id)
    await callback.answer()

@router.message(AdminStates.waiting_user_id, F.text)
async def process_user_id(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: uid = int(message.text.strip())
    except: return await message.answer("❌ ID должен быть числом.")
    await state.update_data(target_uid=uid)
    await message.answer("На сколько дней выдать?")
    await state.set_state(AdminStates.waiting_days)

@router.message(AdminStates.waiting_days, F.text)
async def process_days(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: days = int(message.text.strip())
    except: return await message.answer("❌ Нужно число.")
    data = await state.get_data()
    uid = data.get("target_uid")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_paid = TRUE, subscription_end = GREATEST(COALESCE(subscription_end, NOW()), NOW()) + make_interval(days => $1) WHERE user_id = $2", days, uid)
    await state.clear()
    await message.answer(f"✅ Выдано {days} дней.")

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, username, is_paid, is_banned FROM users ORDER BY created_at DESC LIMIT 20")
    kb = []
    for r in rows:
        status = "💎" if r["is_paid"] else "👤"
        if r["is_banned"]: status = "⛔️"
        name = f"@{r['username']}" if r["username"] else str(r["user_id"])
        kb.append([InlineKeyboardButton(text=f"{status} {name}", callback_data=f"admin_user_{r['user_id']}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")])
    await safe_edit(callback.message, "👥 <b>Последние 20 юзеров:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_user_"))
async def admin_user_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    uid = int(callback.data.replace("admin_user_", ""))
    user = await get_user(uid)
    if not user: return await callback.answer("Нет такого", show_alert=True)
    sub = user.get("subscription_end").strftime("%d.%m.%Y") if user.get("subscription_end") else "Нет"
    text = f"👤 <b>ID:</b> <code>{uid}</code>\nИмя: {user['first_name']}\nПодписка: {sub}\nТриал: {'✅' if user.get('trial_used') else '❌'}"
    await safe_edit(callback.message, text, reply_markup=user_kb(uid))
    await callback.answer()

@router.callback_query(F.data.startswith("admin_ban_"))
async def admin_ban(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    uid = int(callback.data.replace("admin_ban_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT is_banned FROM users WHERE user_id = $1", uid)
        new_val = not row["is_banned"]
        await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", new_val, uid)
    await callback.answer("Забанен" if new_val else "Разбанен")
    await admin_user_view(callback)

@router.callback_query(F.data.startswith("admin_reset_trial_"))
async def admin_reset_trial(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    uid = int(callback.data.replace("admin_reset_trial_", ""))
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_used = FALSE WHERE user_id = $1", uid)
    await callback.answer("✅ Триал сброшен", show_alert=True)
    await admin_user_view(callback)

@router.callback_query(F.data == "admin_trial")
async def admin_trial(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        trial_used = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_used = TRUE")
    trial_enabled = await get_setting("trial_enabled", "true") == "true"
    trial_days = await get_setting("trial_days", "3")
    status = "🟢 Включен" if trial_enabled else "🔴 Выключен"
    text = f"🎁 <b>ТРИАЛ</b>\n➖➖➖➖➖➖➖➖➖➖\nСтатус: <b>{status}</b>\nСрок: <b>{trial_days} дней</b>\nИспользовали: <b>{trial_used}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выключить" if trial_enabled else "✅ Включить", callback_data="admin_trial_toggle")],
        [InlineKeyboardButton(text="✏️ Изменить срок", callback_data="admin_trial_edit")],
        [InlineKeyboardButton(text="🔄 Сбросить", callback_data="admin_trial_reset")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")],
    ])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "admin_trial_toggle")
async def admin_trial_toggle(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    current = await get_setting("trial_enabled", "true")
    await set_setting("trial_enabled", "false" if current == "true" else "true")
    await callback.answer("Статус изменен")
    await admin_trial(callback)

@router.callback_query(F.data == "admin_trial_edit")
async def admin_trial_edit(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "Введи срок триала в днях:")
    await state.set_state(AdminStates.waiting_trial_days)
    await callback.answer()

@router.message(AdminStates.waiting_trial_days, F.text)
async def admin_trial_save(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: days = int(message.text.strip())
    except: return await message.answer("❌ Нужно число.")
    await set_setting("trial_days", str(days))
    await state.clear()
    await message.answer(f"✅ Триал: {days} дней")
    await admin_trial(message)

@router.callback_query(F.data == "admin_trial_reset")
async def admin_trial_reset(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_used = FALSE")
    await callback.answer("✅ Сброшено у всех", show_alert=True)
    await admin_trial(callback)

@router.callback_query(F.data == "admin_manage_admins")
async def admin_manage_admins(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    text = f"👑 <b>АДМИНЫ</b>\n➖➖➖➖➖➖➖➖➖➖\n" + "\n".join(f"• <code>{a}</code>" for a in ADMINS)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить", callback_data="admin_add_admin")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="stub_admin")]])
    await safe_edit(callback.message, text, reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "admin_add_admin")
async def admin_add_admin(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "Введи ID нового админа:")
    await state.set_state(AdminStates.waiting_admin_id)
    await callback.answer()

@router.message(AdminStates.waiting_admin_id, F.text)
async def admin_save_admin(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    try: uid = int(message.text.strip())
    except: return await message.answer("❌ Нужен ID.")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_admin = TRUE WHERE user_id = $1", uid)
    if uid not in ADMINS: ADMINS.append(uid)
    await state.clear()
    await message.answer(f"✅ {uid} теперь админ!")

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id): return
    await safe_edit(callback.message, "📢 Введи текст рассылки для всех юзеров:")
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.answer()

@router.message(AdminStates.waiting_broadcast, F.text)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id): return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
    sent = 0
    for r in rows:
        try:
            await message.bot.send_message(r["user_id"], message.text)
            sent += 1
        except: pass
    await state.clear()
    await message.answer(f"✅ Отправлено: {sent}")

@router.callback_query(F.data == "admin_stop")
async def admin_stop(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id): return
    await ban_all_non_admins()
    await safe_edit(callback.message, "🚨 <b>EMERGENCY STOP</b>\n\nВсе юзеры забанены. Бот остановлен.", reply_markup=admin_kb())
    await callback.answer()