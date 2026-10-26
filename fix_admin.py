import re
from pathlib import Path

p = Path("handlers/admin.py")
content = p.read_text(encoding="utf-8")

# admin_ban и admin_promote вызывают admin_user_view через подмену data
content = content.replace(
    '''    await callback.answer("Забанен" if new_val else "Разбанен")
    callback.data = f"admin_user_{uid}"
    await admin_user_view(callback)''',
    '''    await callback.answer("Забанен" if new_val else "Разбанен")
    await _show_user(callback, uid)'''
)

content = content.replace(
    '''    await callback.answer("Админ" if new_val else "Не админ")
    callback.data = f"admin_user_{uid}"
    await admin_user_view(callback)''',
    '''    await callback.answer("Админ" if new_val else "Не админ")
    await _show_user(callback, uid)'''
)

# Разбить admin_user_view на роутер + _show_user
old_view = '''@router.callback_query(F.data.startswith("admin_user_") & ~F.data.startswith("admin_user_strats_"))
async def admin_user_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_user_", ""))
    pool = await get_pool()'''

new_view = '''@router.callback_query(F.data.startswith("admin_user_") & ~F.data.startswith("admin_user_strats_"))
async def admin_user_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    uid = int(callback.data.replace("admin_user_", ""))
    await _show_user(callback, uid)


async def _show_user(callback: CallbackQuery, uid: int):
    pool = await get_pool()'''

if old_view in content:
    content = content.replace(old_view, new_view)
    print("OK: admin_user_view разбит")
else:
    print("WARN: admin_user_view не найден")

p.write_text(content, encoding="utf-8", newline="")
print("ГОТОВО")