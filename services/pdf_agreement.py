import logging
import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, black

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "DejaVuSans.ttf")

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont("DejaVuSans", FONT_PATH))
    FONT_NAME = "DejaVuSans"
else:
    logger.error(f"Шрифт не найден: {FONT_PATH}")
    FONT_NAME = "Helvetica"

def create_agreement_pdf(user_id: int, username: str, first_name: str) -> str:
    filename = f"agreement_{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    c.setFont(FONT_NAME, 16)
    c.drawCentredString(width / 2, height - 60, "ПОЛЬЗОВАТЕЛЬСКОЕ СОГЛАШЕНИЕ")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(width / 2, height - 75, "о принятии рисков при торговле на реальном рынке")

    c.setFont(FONT_NAME, 9)
    y = height - 110
    
    text_lines = [
        f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        f"Telegram ID: {user_id}",
        f"Имя: {first_name or '-'}",
        f"Username: @{username or '-'}",
        "",
        "Настоящим я подтверждаю, что:",
        "1. Я ознакомлен с рисками торговли криптовалютами и производными инструментами (фьючерсы).",
        "2. Я понимаю, что использование плеча может привести к полной и быстрой потере депозита.",
        "3. Владелец бота, Разработчик, Администрация и любые аффилированные лица предоставляют доступ к программному обеспечению строго на условиях 'как есть' (AS IS).",
        "4. Владелец, Разработчик и Администрация не несут никакой финансовой, юридической или иной ответственности за любые прямые или косвенные убытки, упущенную выгоду или эмоциональный ущерб, возникшие в результате использования бота.",
        "5. Бот не является инвестиционным советником, брокером или доверительным управляющим. Все сигналы носят исключительно информационный характер.",
        "6. Любые торговые решения принимаются мной самостоятельно и на мой собственный страх и риск.",
        "7. Я обязуюсь не предъявлять претензии, иски или требования к Владельцу, Разработчику или Администрации в случае убытков.",
        "8. Я подтверждаю, что действую в рамках законодательства своей юрисдикции и достиг совершеннолетия.",
        "",
        "Я принимаю данные условия и перехожу в режим реальной торговли (Mainnet) на свой страх и риск."
    ]

    for line in text_lines:
        # Перенос длинных строк
        if len(line) > 95:
            words = line.split()
            current_line = ""
            for word in words:
                if len(current_line) + len(word) < 95:
                    current_line += word + " "
                else:
                    c.drawString(40, y, current_line.strip())
                    y -= 14
                    current_line = word + " "
            if current_line:
                c.drawString(40, y, current_line.strip())
                y -= 14
        else:
            c.drawString(40, y, line)
            y -= 14

    c.setFont(FONT_NAME, 11)
    c.drawString(40, y - 30, "Подпись (Telegram ID):")
    c.line(40, y - 35, 250, y - 35)
    c.drawString(40, y - 50, f"{user_id}")

    c.save()
    return filename