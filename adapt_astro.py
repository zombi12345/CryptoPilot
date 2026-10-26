import re
import shutil
from pathlib import Path

# Путь к AstroBot (измени, если папка называется иначе)
ASTRO_DIR = Path(r"C:\Users\User\Desktop\AstroBot_clean")
OUR_DIR = Path(r"C:\Users\User\Desktop\CryptoPilot")

# 1. Копируем файлы
files_to_copy = ["admin_simple.py", "admin_ads.py"]
for f in files_to_copy:
    src = ASTRO_DIR / "handlers" / f
    dst = OUR_DIR / "handlers" / f
    if src.exists():
        shutil.copy(src, dst)
        print(f"Скопирован {f}")
    else:
        print(f"НЕ НАЙДЕН: {src}")

# 2. Адаптируем admin_simple.py
admin_path = OUR_DIR / "handlers" / "admin_simple.py"
if admin_path.exists():
    content = admin_path.read_text(encoding="utf-8")
    
    # Меняем импорты БД
    content = content.replace("from database.postgres_db import", "from database import")
    content = content.replace("from database import (\n    get_pool,", "from database import (\n    get_pool,")
    
    # Меняем названия callback_data (чтобы не конфликтовали)
    content = content.replace('F.data == "admin_panel"', 'F.data == "stub_admin"')
    content = content.replace('callback_data="admin_panel"', 'callback_data="stub_admin"')
    
    # Убираем астрологию (AI-лимиты, факты, кэш), оставляем только то, что нужно нам
    # Проще всего переписать клавиатуру
    old_kb = re.search(r'def admin_main_keyboard\(.*?\n\n', content, re.DOTALL)
    if old_kb:
        new_kb = '''def admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💰 Цены", callback_data="admin_pricing")],
        [InlineKeyboardButton(text="⭐ Баланс", callback_data="admin_balance")],
        [InlineKeyboardButton(text="📢 Реклама", callback_data="admin_ads")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🚨 STOP", callback_data="admin_stop")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])

'''
        content = content[:old_kb.start()] + new_kb + content[old_kb.end():]
    
    admin_path.write_text(content, encoding="utf-8")
    print("Адаптирован admin_simple.py")

# 3. Адаптируем admin_ads.py
ads_path = OUR_DIR / "handlers" / "admin_ads.py"
if ads_path.exists():
    content = ads_path.read_text(encoding="utf-8")
    content = content.replace("from database.postgres_db import", "from database import")
    ads_path.write_text(content, encoding="utf-8")
    print("Адаптирован admin_ads.py")

print("ГОТОВО")