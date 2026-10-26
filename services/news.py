import logging
import requests
import xml.etree.ElementTree as ET
from services.ai_client import chat

logger = logging.getLogger(__name__)

FEEDS = [
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

def get_crypto_news(limit: int = 5):
    news = []
    for source_name, url in FEEDS:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.find("title")
                link = item.find("link")
                if title is not None and title.text:
                    news.append({
                        "title": title.text.strip(),
                        "link": link.text if link is not None else "",
                        "source": source_name,
                    })
                if len(news) >= limit:
                    break
        except Exception as e:
            logger.warning(f"RSS {source_name} error: {e}")
        if len(news) >= limit:
            break
    if not news:
        return {"error": "Не удалось загрузить новости"}
    return {"ok": True, "news": news[:limit]}


async def translate_titles(titles: list) -> list:
    """Переводит заголовки на русский через AI."""
    if not titles:
        return []
    text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
    messages = [
        {"role": "system", "content": "Ты переводчик. Переведи заголовки новостей на русский язык. Верни только переводы, каждый с новой строки, без нумерации."},
        {"role": "user", "content": text},
    ]
    result = await chat(messages, max_tokens=500)
    if not result:
        return titles
    lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
    if len(lines) == len(titles):
        return lines
    return titles