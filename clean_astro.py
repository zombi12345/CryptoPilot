import re
from pathlib import Path

OUR_DIR = Path(r"C:\Users\User\Desktop\CryptoPilot")
admin_path = OUR_DIR / "handlers" / "admin_simple.py"
ads_path = OUR_DIR / "handlers" / "admin_ads.py"

def clean_file(path):
    if not path.exists(): return
    content = path.read_text(encoding="utf-8")
    
    # 1. Удаляем импорты locales
    content = re.sub(r"from locales.*?\n", "", content)
    content = re.sub(r"from handlers\.locales.*?\n", "", content)
    
    # 2. Убираем функцию получения языка
    content = re.sub(r"async def _admin_lang\(.*?\n\n", "", content, flags=re.DOTALL)
    content = re.sub(r"async def _lang\(.*?\n\n", "", content, flags=re.DOTALL)
    
    # 3. Заменяем t("KEY", lang) на просто "KEY" (чтобы не падало)
    # Ищем t("SOMETHING", lang) и заменяем на "SOMETHING"
    content = re.sub(r't\("[^"]+",\s*lang\)', '"Текст"', content)
    content = re.sub(r"t\('[^']+',\s*lang\)", '"Текст"', content)
    
    # 4. Убираем передачу lang в функции, если она осталась
    content = content.replace(", lang=lang", "")
    content = content.replace("lang = await _admin_lang(callback.from_user.id)", "")
    content = content.replace("lang = await _lang(message.from_user.id)", "")
    
    # 5. Если остались вызовы is_admin, добавляем заглушку (в AstroBot есть своя is_admin)
    if "await is_admin(" in content and "async def is_admin(" not in content and "from database import is_admin" not in content:
        content = content.replace("from database import", "from database import is_admin,")
    
    path.write_text(content, encoding="utf-8")
    print(f"Очищен {path.name}")

clean_file(admin_path)
clean_file(ads_path)
print("ГОТОВО")