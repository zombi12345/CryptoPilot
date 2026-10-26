import logging
import os
import requests

logger = logging.getLogger(__name__)

BARGO_KEY = os.getenv("BARGO_API_KEY", "")

def get_congress_trades(ticker: str, limit: int = 10):
    """Сделки конгрессменов по тикеру (Bargo, бесплатно)."""
    ticker = ticker.upper().strip()
    url = f"https://www.bargo.ai/free-apis/congress/v1/trades/{ticker}"
    params = {"limit": limit}
    headers = {"X-Api-Key": BARGO_KEY} if BARGO_KEY else {}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return {"ok": True, "trades": data.get("trades", [])}
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}