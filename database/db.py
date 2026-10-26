import json
import logging
import asyncpg
from config import DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

logger = logging.getLogger(__name__)

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=DB_HOST,
            port=int(DB_PORT),
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            min_size=1,
            max_size=5,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _decode_strategy(row):
    if not row:
        return None
    d = dict(row)
    for field in ("indicators", "entry_rules", "exit_rules", "risk"):
        val = d.get(field)
        if isinstance(val, str):
            try:
                d[field] = json.loads(val)
            except Exception:
                d[field] = [] if field != "risk" else {}
    return d


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                agreed_at TIMESTAMP,
                is_admin BOOLEAN DEFAULT FALSE,
                max_leverage NUMERIC DEFAULT 3,
                max_risk_pct NUMERIC DEFAULT 2,
                deposit_limit NUMERIC DEFAULT 100,
                daily_loss_limit_pct NUMERIC DEFAULT 3,
                daily_trades_limit INTEGER DEFAULT 10,
                allow_spot BOOLEAN DEFAULT TRUE,
                allow_futures BOOLEAN DEFAULT FALSE,
                allow_testnet BOOLEAN DEFAULT TRUE,
                allow_mainnet BOOLEAN DEFAULT FALSE,
                is_banned BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                preset_id TEXT,
                indicators JSONB NOT NULL DEFAULT '[]'::jsonb,
                entry_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
                exit_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
                risk JSONB NOT NULL DEFAULT '{}'::jsonb,
                logic TEXT DEFAULT 'AND',
                is_active BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS backtests (
                id SERIAL PRIMARY KEY,
                strategy_id INTEGER REFERENCES strategies(id) ON DELETE CASCADE,
                user_id BIGINT,
                symbol TEXT,
                timeframe TEXT,
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                total_return_pct NUMERIC,
                max_drawdown_pct NUMERIC,
                win_rate NUMERIC,
                profit_factor NUMERIC,
                total_trades INTEGER,
                equity_curve JSONB,
                trades JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS book_summaries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                filename TEXT NOT NULL,
                summary JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, filename)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                exchange TEXT,
                mode TEXT,
                market TEXT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount NUMERIC,
                entry_price NUMERIC,
                sl NUMERIC,
                tp NUMERIC,
                leverage NUMERIC,
                order_id TEXT,
                status TEXT DEFAULT 'open',
                close_price NUMERIC,
                pnl NUMERIC,
                created_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_keys (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                exchange TEXT NOT NULL,
                mode TEXT NOT NULL,
                market TEXT NOT NULL,
                api_key_enc TEXT NOT NULL,
                secret_enc TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(user_id, exchange, mode, market)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS global_settings (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        # Дефолты
        defaults = {
            "default_max_leverage": 3,
            "default_max_risk_pct": 2,
            "default_deposit_limit": 100,
            "default_daily_loss_limit_pct": 3,
            "default_daily_trades_limit": 10,
            "default_allow_spot": True,
            "default_allow_futures": False,
        }
        for k, v in defaults.items():
            await conn.execute("""
                INSERT INTO global_settings (key, value)
                VALUES ($1, $2::jsonb)
                ON CONFLICT (key) DO NOTHING
            """, k, json.dumps(v))
    logger.info("БД инициализирована")


async def get_global_setting(key, default=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM global_settings WHERE key = $1", key)
    if not row:
        return default
    val = row["value"]
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return default
    return val


async def set_global_setting(key, value):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO global_settings (key, value, updated_at)
            VALUES ($1, $2::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = $2::jsonb, updated_at = NOW()
        """, key, json.dumps(value))


async def get_all_global_settings():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value FROM global_settings")
    out = {}
    for r in rows:
        val = r["value"]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                val = None
        out[r["key"]] = val
    return out


async def create_user_if_missing(user_id, username, first_name):
    pool = await get_pool()
    d = await get_all_global_settings()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name,
                max_leverage, max_risk_pct, deposit_limit,
                daily_loss_limit_pct, daily_trades_limit,
                allow_spot, allow_futures)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name,
            d.get("default_max_leverage", 3),
            d.get("default_max_risk_pct", 2),
            d.get("default_deposit_limit", 100),
            d.get("default_daily_loss_limit_pct", 3),
            d.get("default_daily_trades_limit", 10),
            d.get("default_allow_spot", True),
            d.get("default_allow_futures", False),
        )


async def set_agreed(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET agreed_at = NOW() WHERE user_id = $1 AND agreed_at IS NULL",
            user_id,
        )


async def get_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def list_strategies(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM strategies WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
        return [_decode_strategy(r) for r in rows]


async def get_strategy(strategy_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM strategies WHERE id = $1", strategy_id)
        return _decode_strategy(row)


async def create_strategy(user_id, name, symbol, timeframe, preset_id, indicators, entry_rules, exit_rules, risk, logic):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO strategies (user_id, name, symbol, timeframe, preset_id, indicators, entry_rules, exit_rules, risk, logic)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8::jsonb, $9::jsonb, $10)
            RETURNING id
        """, user_id, name, symbol, timeframe, preset_id,
            json.dumps(indicators),
            json.dumps(entry_rules),
            json.dumps(exit_rules),
            json.dumps(risk),
            logic,
        )
        return row["id"]


async def toggle_strategy(strategy_id, is_active):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE strategies SET is_active = $1 WHERE id = $2",
            is_active, strategy_id,
        )


async def delete_strategy(strategy_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM strategies WHERE id = $1", strategy_id)


async def save_backtest(strategy_id, user_id, symbol, timeframe, period_start, period_end, metrics, equity_curve, trades):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO backtests (strategy_id, user_id, symbol, timeframe, period_start, period_end,
                total_return_pct, max_drawdown_pct, win_rate, profit_factor, total_trades, equity_curve, trades)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb, $13::jsonb)
            RETURNING id
        """, strategy_id, user_id, symbol, timeframe, period_start, period_end,
            metrics["total_return_pct"], metrics["max_drawdown_pct"], metrics["win_rate"],
            metrics["profit_factor"], metrics["total_trades"],
            json.dumps(equity_curve),
            json.dumps(trades),
        )
        return row["id"]


async def list_backtests(strategy_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM backtests WHERE strategy_id = $1 ORDER BY created_at DESC LIMIT 10",
            strategy_id,
        )
        return [dict(r) for r in rows]


async def save_book_summary(user_id, filename, summary):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO book_summaries (user_id, filename, summary)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (user_id, filename) DO UPDATE SET summary = $3::jsonb
        """, user_id, filename, json.dumps(summary))


async def get_book_summary(user_id, filename):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT summary FROM book_summaries WHERE user_id = $1 AND filename = $2",
            user_id, filename,
        )
        if not row:
            return None
        val = row["summary"]
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return None
        return val


async def get_all_book_summaries(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT filename, summary FROM book_summaries WHERE user_id = $1",
            user_id,
        )
        out = {}
        for r in rows:
            val = r["summary"]
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    continue
            out[r["filename"]] = val
        return out


async def delete_book_summary(user_id, filename):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM book_summaries WHERE user_id = $1 AND filename = $2",
            user_id, filename,
        )


async def unban_all():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = FALSE")


async def ban_all_non_admins():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = TRUE WHERE is_admin = FALSE")

async def add_exchange_key(user_id, exchange, mode, market, api_key_enc, secret_enc):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO exchange_keys (user_id, exchange, mode, market, api_key_enc, secret_enc)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (user_id, exchange, mode, market) DO UPDATE
            SET api_key_enc = $5, secret_enc = $6, created_at = NOW()
        """, user_id, exchange, mode, market, api_key_enc, secret_enc)


async def get_exchange_keys(user_id, exchange, mode, market):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT api_key_enc, secret_enc FROM exchange_keys
            WHERE user_id = $1 AND exchange = $2 AND mode = $3 AND market = $4
        """, user_id, exchange, mode, market)
        return dict(row) if row else None


async def list_exchange_keys(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT exchange, mode, market, created_at FROM exchange_keys
            WHERE user_id = $1 ORDER BY created_at DESC
        """, user_id)
        return [dict(r) for r in rows]


async def delete_exchange_key(user_id, exchange, mode, market):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM exchange_keys
            WHERE user_id = $1 AND exchange = $2 AND mode = $3 AND market = $4
        """, user_id, exchange, mode, market)


async def save_order(user_id, exchange, mode, market, symbol, side, amount, entry_price, sl, tp, leverage, order_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO orders (user_id, exchange, mode, market, symbol, side, amount, entry_price, sl, tp, leverage, order_id, status)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'open')
        """, user_id, exchange, mode, market, symbol, side, amount, entry_price, sl, tp, leverage, order_id)


async def close_order_in_db(user_id, symbol, close_price, pnl):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE orders SET status = 'closed', close_price = $1, pnl = $2, closed_at = NOW()
            WHERE id = (
                SELECT id FROM orders
                WHERE user_id = $3 AND symbol = $4 AND status = 'open'
                ORDER BY created_at DESC LIMIT 1
            )
        """, close_price, pnl, user_id, symbol)


async def list_orders(user_id, limit=20):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM orders
            WHERE user_id = $1
            ORDER BY created_at DESC LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]


async def get_orders_stats(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'closed') as closed,
                COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0) as wins,
                COUNT(*) FILTER (WHERE status = 'closed' AND pnl <= 0) as losses,
                COALESCE(SUM(pnl) FILTER (WHERE status = 'closed'), 0) as total_pnl
            FROM orders
            WHERE user_id = $1
        """, user_id)
        return dict(row) if row else {}


async def toggle_auto_trade(user_id, enabled):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET allow_spot = $1 WHERE user_id = $2", enabled, user_id) # Используем allow_spot как флаг для простоты


async def get_auto_trade_users():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE allow_spot = TRUE AND is_banned = FALSE")
        return [r["user_id"] for r in rows]


async def get_daily_pnl(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Считаем PnL за сегодня
        row = await conn.fetchrow("""
            SELECT COALESCE(SUM(pnl), 0) as pnl
            FROM orders
            WHERE user_id = $1 AND status = 'closed' AND closed_at >= CURRENT_DATE
        """, user_id)
        return float(row["pnl"]) if row else 0.0


async def get_auto_settings(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else {}


async def update_auto_settings(user_id, risk_pct, leverage, trades_limit, deposit_limit):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET 
                max_risk_pct = $1, 
                max_leverage = $2, 
                daily_trades_limit = $3, 
                deposit_limit = $4
            WHERE user_id = $5
        """, risk_pct, leverage, trades_limit, deposit_limit, user_id)
