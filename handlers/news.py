import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from services.news import get_crypto_news, translate_titles

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit(msg, text, reply_markup=None, parse_mode="HTML"):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            await msg.edit_text(text, parse_mode=parse_mode)
    except Exception:
        pass


def news_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="stub_news")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_news")
async def show_news(callback: CallbackQuery):
    # 1. СРАЗУ меняем текст на "Загружаю", чтобы юзер видел прогресс
    await safe_edit(callback.message, "⏳ Загружаю и перевожу новости...")
    
    # 2. СРАЗУ отвечаем на callback, чтобы Telegram не выдал ошибку таймаута
    await callback.answer()
    
    # 3. Теперь спокойно грузим новости
    res = get_crypto_news(limit=5)
    
    if not res.get("ok"):
        await safe_edit(callback.message, f"❌ Ошибка: {res.get('error')}", reply_markup=news_kb())
        return
        
    news = res.get("news", [])
    if not news:
        await safe_edit(callback.message, "📰 Новостей пока нет.", reply_markup=news_kb())
        return

    # 4. Переводим
    titles = [n["title"] for n in news]
    translated = await translate_titles(titles)

    text = "📰 <b>ПОСЛЕДНИЕ НОВОСТИ</b>\n\n"
    
    for i, n in enumerate(news):
        title_ru = translated[i] if i < len(translated) else n["title"]
        source = n["source"]
        link = n["link"]
        
        if link:
            text += f"• <a href='{link}'><b>{title_ru}</b></a>\n  <i>{source}</i>\n\n"
        else:
            text += f"• <b>{title_ru}</b>\n  <i>{source}</i>\n\n"
        
    if len(text) > 4000:
        text = text[:4000] + "\n(обрезано)"
        
    # 5. Показываем результат
    await safe_edit(callback.message, text, reply_markup=news_kb(), parse_mode="HTML")