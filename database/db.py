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
    logger.info("БД инициализирована")


async def create_user_if_missing(user_id, username, first_name):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name)


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
