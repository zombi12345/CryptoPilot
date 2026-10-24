import logging
import pandas as pd

logger = logging.getLogger(__name__)


def evaluate_rule(row, prev_row, rule):
    ind = rule.get("indicator")
    op = rule.get("operator")
    if not ind or not op:
        return False
    left = row.get(ind)
    if left is None or pd.isna(left):
        return False

    right = None
    if "value" in rule:
        right = rule["value"]
    elif "value_ref" in rule:
        right = row.get(rule["value_ref"])
        if right is None or pd.isna(right):
            return False
    else:
        return False

    try:
        if op == ">": return left > right
        if op == "<": return left < right
        if op == ">=": return left >= right
        if op == "<=": return left <= right
        if op == "==": return left == right
        if op == "!=": return left != right
        if op == "crosses_above":
            if prev_row is None:
                return False
            pl = prev_row.get(ind)
            pr = prev_row.get(rule["value_ref"])
            if any(pd.isna(x) for x in (pl, pr)):
                return False
            return pl <= pr and left > right
        if op == "crosses_below":
            if prev_row is None:
                return False
            pl = prev_row.get(ind)
            pr = prev_row.get(rule["value_ref"])
            if any(pd.isna(x) for x in (pl, pr)):
                return False
            return pl >= pr and left < right
    except Exception as e:
        logger.warning(f"evaluate_rule error: {e}")
        return False
    return False


def evaluate_rules(row, prev_row, rules, logic="AND"):
    if not rules:
        return False
    results = [evaluate_rule(row, prev_row, r) for r in rules]
    return all(results) if logic == "AND" else any(results)


def run_backtest(df, strategy, initial_balance=1000.0, fee_pct=0.1, slippage_pct=0.05):
    if df.empty or len(df) < 50:
        return {"error": "Недостаточно данных"}

    entry_rules = strategy.get("entry_rules", [])
    exit_rules = strategy.get("exit_rules", [])
    risk = strategy.get("risk", {})
    entry_logic = strategy.get("logic", "AND")
    exit_logic = "OR"

    sl_pct = float(risk.get("stop_loss_pct", 2.0))
    tp_pct = float(risk.get("take_profit_pct", 4.0))
    risk_per_trade_pct = float(risk.get("risk_per_trade_pct", 1.0))

    balance = initial_balance
    position = None
    trades = []
    equity_curve = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        ts = row["ts"]

        if position is not None:
            hit_sl = (
                (position["side"] == "long" and row["low"] <= position["sl"]) or
                (position["side"] == "short" and row["high"] >= position["sl"])
            )
            hit_tp = (
                (position["side"] == "long" and row["high"] >= position["tp"]) or
                (position["side"] == "short" and row["low"] <= position["tp"])
            )
            exit_price = None
            reason = ""
            if hit_sl and hit_tp:
                exit_price = position["sl"]
                reason = "SL_ambiguous"
            elif hit_sl:
                exit_price = position["sl"]
                reason = "SL"
            elif hit_tp:
                exit_price = position["tp"]
                reason = "TP"
            elif evaluate_rules(row, prev, exit_rules, exit_logic):
                exit_price = row["close"]
                reason = "signal"

            if exit_price is not None:
                exit_price = exit_price * (1 - slippage_pct / 100) if position["side"] == "long" else exit_price * (1 + slippage_pct / 100)
                if position["side"] == "long":
                    pnl = (exit_price - position["entry"]) * position["size"]
                else:
                    pnl = (position["entry"] - exit_price) * position["size"]
                fee = (position["entry"] + exit_price) * position["size"] * fee_pct / 100
                pnl -= fee
                balance += pnl
                trades.append({
                    "entry_time": position["entry_time"].isoformat(),
                    "exit_time": ts.isoformat(),
                    "side": position["side"],
                    "entry": position["entry"],
                    "exit": exit_price,
                    "size": position["size"],
                    "pnl": pnl,
                    "reason": reason,
                })
                position = None

        if position is None and evaluate_rules(row, prev, entry_rules, entry_logic):
            entry_price = row["close"] * (1 + slippage_pct / 100)
            if row["close"] <= 0:
                equity_curve.append({"t": ts.isoformat(), "balance": balance})
                continue
            size = (balance * risk_per_trade_pct / 100) / (entry_price * sl_pct / 100) if sl_pct > 0 else 0
            max_size = balance / entry_price
            size = min(size, max_size)
            if size > 0:
                position = {
                    "entry_time": ts,
                    "entry": entry_price,
                    "side": "long",
                    "size": size,
                    "sl": entry_price * (1 - sl_pct / 100),
                    "tp": entry_price * (1 + tp_pct / 100),
                }

        equity_curve.append({"t": ts.isoformat(), "balance": balance})

    if position is not None:
        last = df.iloc[-1]
        pnl = (last["close"] - position["entry"]) * position["size"]
        balance += pnl
        trades.append({
            "entry_time": position["entry_time"].isoformat(),
            "exit_time": last["ts"].isoformat(),
            "side": position["side"],
            "entry": position["entry"],
            "exit": last["close"],
            "size": position["size"],
            "pnl": pnl,
            "reason": "end_of_data",
        })

    total_return_pct = (balance / initial_balance - 1) * 100
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)

    peak = initial_balance
    max_dd = 0.0
    for pt in equity_curve:
        peak = max(peak, pt["balance"])
        dd = (peak - pt["balance"]) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "total_trades": len(trades),
        "equity_curve": equity_curve,
        "trades": trades,
    }