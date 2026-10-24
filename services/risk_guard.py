import logging
from database import get_user

logger = logging.getLogger(__name__)

LEVELS = {
    "low": {"max_leverage": 3, "max_risk_pct": 2},
    "medium": {"max_leverage": 5, "max_risk_pct": 5},
    "high": {"max_leverage": 10, "max_risk_pct": 10},
    "critical": {"max_leverage": 999, "max_risk_pct": 999},
}


def classify_risk(leverage: float, risk_pct: float, has_sl: bool) -> str:
    if not has_sl:
        return "critical"
    if leverage > 10 or risk_pct > 10:
        return "critical"
    if leverage > 5 or risk_pct > 5:
        return "high"
    if leverage > 3 or risk_pct > 2:
        return "medium"
    return "low"


async def check_trade(user_id: int, symbol: str, side: str, amount: float, price: float, leverage: float, risk_pct: float, has_sl: bool, has_tp: bool) -> dict:
    user = await get_user(user_id)
    if not user:
        return {"ok": False, "reason": "Пользователь не найден"}

    if user.get("is_banned"):
        return {"ok": False, "reason": "Аккаунт забанен"}

    if not user.get("agreed_at"):
        return {"ok": False, "reason": "Сначала примите соглашение (/start)"}

    user_max_leverage = float(user.get("max_leverage") or 3)
    user_max_risk = float(user.get("max_risk_pct") or 2)
    deposit_limit = float(user.get("deposit_limit") or 100)

    if leverage > user_max_leverage:
        return {"ok": False, "reason": f"Плечо {leverage}x превышает лимит {user_max_leverage}x"}

    if risk_pct > user_max_risk:
        return {"ok": False, "reason": f"Риск {risk_pct}% превышает лимит {user_max_risk}%"}

    position_value = amount * price
    if position_value > deposit_limit:
        return {"ok": False, "reason": f"Размер позиции ${position_value:.2f} превышает лимит депозита ${deposit_limit:.2f}"}

    if not has_sl:
        return {"ok": False, "reason": "Stop-loss обязателен. Без SL торговля запрещена."}

    if not has_tp:
        return {"ok": False, "reason": "Take-profit обязателен. Без TP торговля запрещена."}

    level = classify_risk(leverage, risk_pct, has_sl)
    warning = None
    if level == "medium":
        warning = f"Средний риск: плечо {leverage}x, риск {risk_pct}%"
    elif level == "high":
        warning = f"Высокий риск: плечо {leverage}x, риск {risk_pct}%. Двойное подтверждение."

    return {
        "ok": True,
        "level": level,
        "warning": warning,
        "position_value": position_value,
        "leverage": leverage,
        "risk_pct": risk_pct,
    }