import asyncpg
import logging
import json
from datetime import datetime, timedelta, date
from config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, FREE_MODE, ADMINS
)

logger = logging.getLogger(__name__)


class Database:
    pool = None

    @classmethod
    async def create_pool(cls):
        if cls.pool is None:
            cls.pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=int(DB_PORT),
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                min_size=1,
                max_size=5,
                ssl="require",
                statement_cache_size=0,
            )
            logger.info("✅ Пул соединений с PostgreSQL создан.")
        return cls.pool

    @classmethod
    async def close_pool(cls):
        if cls.pool:
            await cls.pool.close()
            cls.pool = None
            logger.info("Пул соединений закрыт.")


db = Database()


# ============================================================
# НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ============================================================
DEFAULT_PRICING = {
    "7":  {"days": 7,  "stars": 99},
    "30": {"days": 30, "stars": 299},
    "90": {"days": 90, "stars": 699},
}

DEFAULT_TRIAL = {
    "enabled": True,
    "days": 1,
}

DEFAULT_AI_LIMITS = {
    "free": 20,
    "premium": 100,
    "count_cached": False,  # считать ли кэшированные ответы
}


async def init_postgres_db():
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        # --- USERS ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                birth_date TEXT,
                birth_time TEXT,
                birth_place TEXT,
                is_paid BOOLEAN DEFAULT FALSE,
                subscription_end TEXT,
                trial_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Get existing columns first (1 fast query)
        existing_cols = set()
        try:
            rows = await conn.fetch("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'users'
            """)
            existing_cols = {r["column_name"] for r in rows}
        except Exception as e:
            logger.warning(f"Failed to read users columns: {e}")

        # Migrations: only ADD missing columns
        for col, col_type in [
            ("gender", "TEXT"),
            ("bio", "TEXT"),
            ("interests", "TEXT"),
            ("goals", "TEXT"),
            ("relationship_status", "TEXT"),
            ("ai_notes", "TEXT"),
            ("profile_completed", "BOOLEAN DEFAULT FALSE"),
        ]:
            if col in existing_cols:
                continue
            try:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                logger.info(f"Added column: {col}")
            except Exception as e:
                logger.warning(f"Migration {col}: {e}")

        # --- PAYMENTS ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                stars_paid INTEGER NOT NULL,
                payment_id TEXT UNIQUE NOT NULL,
                days INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- MIGRATION: колонка days в payments ---
        try:
            await conn.execute(
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS days INTEGER DEFAULT 0"
            )
        except Exception as e:
            logger.warning(f"Миграция payments.days: {e}")

        
        # --- MIGRATION: language (multilang) ---
        try:
            from config import MULTILANG_ENABLED
            if MULTILANG_ENABLED:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ru'"
                )
                logger.info("✅ Колонка users.language создана/проверена")
        except Exception as e:
            logger.warning(f"Миграция language: {e}")

# --- REQUESTS ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- SETTINGS ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- USER_NOTES ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_notes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                note TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes(user_id)
        """)

        # --- AI_HISTORY ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                request_type TEXT NOT NULL,
                request_key TEXT,
                question TEXT,
                answer TEXT NOT NULL,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_history_key ON ai_history(request_key)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_history_user ON ai_history(user_id)
        """)

        # --- AI_USAGE (счётчик запросов) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id BIGINT NOT NULL,
                usage_date DATE NOT NULL,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            )
        """)

        # --- Инициализация pricing ---
        existing = await conn.fetchval("SELECT value FROM settings WHERE key = 'pricing'")
        if not existing:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2)",
                "pricing", json.dumps(DEFAULT_PRICING, ensure_ascii=False)
            )

        # --- Инициализация trial ---
        existing = await conn.fetchval("SELECT value FROM settings WHERE key = 'trial'")
        if not existing:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2)",
                "trial", json.dumps(DEFAULT_TRIAL, ensure_ascii=False)
            )

        # --- Инициализация ai_limits ---
        existing = await conn.fetchval("SELECT value FROM settings WHERE key = 'ai_limits'")
        if not existing:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2)",
                "ai_limits", json.dumps(DEFAULT_AI_LIMITS, ensure_ascii=False)
            )

    # --- Инициализация рекламы ---
    await init_ads_tables()

    # --- Инициализация дневника настроения ---
    await init_mood_table()

    # --- Инициализация Таро ---
    await init_tarot_table()

    # --- Инициализация рефералов ---
    await init_referrals_table()

    logger.info("✅ Таблицы в PostgreSQL созданы/обновлены")


# ============================================================
# USERS
# ============================================================
async def create_user(user_id: int, username: str = "", first_name: str = ""):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, first_name)


async def get_user(user_id: int):
    # Кэш
    try:
        from services.cache import user_cache
        cached = user_cache.get(f"user_{user_id}")
        if cached is not None:
            return cached
    except Exception:
        pass
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        result = dict(row) if row else None
    try:
        from services.cache import user_cache
        user_cache.set(f"user_{user_id}", result, ttl=20)
    except Exception:
        pass
    return result


async def update_user_field(user_id: int, field: str, value):
    allowed = {
        "birth_date", "birth_time", "birth_place",
        "gender", "bio", "interests", "goals",
        "relationship_status", "ai_notes", "profile_completed",
        "is_paid", "subscription_end", "trial_used",
    }
    if field not in allowed:
        raise ValueError(f"Недопустимое поле: {field}")

    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE users SET {field} = $2 WHERE user_id = $1",
            user_id, value
        )
    # Инвалидируем кэш
    invalidate_user_cache(user_id)


async def update_birth_data(user_id: int, birth_date: str, birth_time: str, birth_place: str):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET birth_date = $2, birth_time = $3, birth_place = $4
            WHERE user_id = $1
        """, user_id, birth_date, birth_time, birth_place)


async def set_subscription(user_id: int, days: int):
    end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE users SET is_paid = TRUE, subscription_end = $2 WHERE user_id = $1
        """, user_id, end_date)


async def is_paid(user_id: int) -> bool:
    if FREE_MODE:
        return True

    if await is_admin(user_id):
        return True

    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_paid, subscription_end FROM users WHERE user_id = $1",
            user_id,
        )
    if not row:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    if row["is_paid"] and row["subscription_end"] and today <= row["subscription_end"]:
        return True
    if row["is_paid"] and row["subscription_end"] and today > row["subscription_end"]:
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_paid = FALSE WHERE user_id = $1", user_id
            )
        return False
    return False


async def has_trial_used(user_id: int) -> bool:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trial_used FROM users WHERE user_id = $1", user_id
        )
        return row["trial_used"] if row else False


async def set_trial_used(user_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET trial_used = TRUE WHERE user_id = $1", user_id
        )


async def reset_all_trials():
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET trial_used = FALSE")


async def count_trial_used() -> int:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE trial_used = TRUE")
    return count or 0


async def add_payment(user_id: int, stars_paid: int, payment_id: str, days: int = 0):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO payments (user_id, stars_paid, payment_id, days)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (payment_id) DO NOTHING
        """, user_id, stars_paid, payment_id, days)


async def get_stats():
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        paid = await conn.fetchval("SELECT COUNT(*) FROM users WHERE is_paid = TRUE")
        total_stars = await conn.fetchval("SELECT COALESCE(SUM(stars_paid), 0) FROM payments")
        total_payments = await conn.fetchval("SELECT COUNT(*) FROM payments")
    return {
        "total_users": total or 0,
        "paid_users": paid or 0,
        "free_users": (total or 0) - (paid or 0),
        "total_stars": total_stars or 0,
        "total_payments": total_payments or 0,
    }


# ============================================================
# USER NOTES
# ============================================================


# ============================================================
# НОРМАЛИЗАЦИЯ ФАКТОВ
# ============================================================
def normalize_fact(fact: str) -> str:
    """
    Приводит факт к 3-му лицу.
    Примеры:
      "люблю кофе" -> "Любит кофе"
      "я программист" -> "Программист"
      "работаю в IT" -> "Работает в IT"
    """
    if not fact:
        return fact
    fact = fact.strip().rstrip(".!?")
    lower = fact.lower()

    # Замены (в порядке приоритета)
    replacements = [
        ("я не люблю ", "Не любит "),
        ("я люблю ", "Любит "),
        ("я не хочу ", "Не хочет "),
        ("я хочу ", "Хочет "),
        ("я не работаю ", "Не работает "),
        ("я работаю ", "Работает "),
        ("я не живу ", "Не живёт "),
        ("я живу в ", "Живёт в "),
        ("я живу ", "Живёт "),
        ("мне не нравится ", "Не нравится "),
        ("мне нравится ", "Нравится "),
        ("у меня есть ", "Есть "),
        ("у меня нет ", "Нет "),
        ("меня зовут ", "Зовут "),
        ("мой ", "Его "),
        ("моя ", "Её "),
        ("моё ", "Его "),
        ("мои ", "Его "),
        ("я ", ""),
    ]

    for old, new in replacements:
        if lower.startswith(old):
            fact = new + fact[len(old):]
            break

    # Первая буква заглавная
    if fact:
        fact = fact[0].upper() + fact[1:]
    return fact.strip()


async def add_user_note(user_id: int, note: str):
    # Нормализуем факт
    note = normalize_fact(note)
    if not note:
        return
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        # Точная проверка
        existing = await conn.fetchval(
            "SELECT id FROM user_notes WHERE user_id = $1 AND LOWER(note) = LOWER($2)",
            user_id, note
        )
        if existing:
            return
        await conn.execute(
            "INSERT INTO user_notes (user_id, note) VALUES ($1, $2)",
            user_id, note
        )


async def get_user_notes(user_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, note, created_at FROM user_notes WHERE user_id = $1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(r) for r in rows]


async def delete_user_note(note_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_notes WHERE id = $1", note_id)


async def clear_user_notes(user_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM user_notes WHERE user_id = $1", user_id)


# ============================================================
# AI HISTORY
# ============================================================
async def save_ai_answer(user_id: int, request_type: str, request_key: str,
                         question: str, answer: str, model: str = "gpt-4o-mini"):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_history (user_id, request_type, request_key, question, answer, model)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, user_id, request_type, request_key, question, answer, model)


async def get_ai_answer(request_key: str, request_type: str = None):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        if request_type:
            row = await conn.fetchrow("""
                SELECT answer, model, created_at FROM ai_history
                WHERE request_key = $1 AND request_type = $2
                ORDER BY created_at DESC LIMIT 1
            """, request_key, request_type)
        else:
            row = await conn.fetchrow("""
                SELECT answer, model, created_at FROM ai_history
                WHERE request_key = $1
                ORDER BY created_at DESC LIMIT 1
            """, request_key)
        return dict(row) if row else None


async def get_ai_history(limit: int = 10):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, user_id, request_type, request_key, question, answer, model, created_at
            FROM ai_history
            ORDER BY created_at DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


async def count_ai_history() -> int:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM ai_history") or 0


async def clean_old_ai_history(days: int = 30):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            f"DELETE FROM ai_history WHERE created_at < NOW() - INTERVAL '{days} days'"
        )
        return result


# ============================================================
# AI LIMITS
# ============================================================
async def get_ai_limits() -> dict:
    data = await get_setting("ai_limits", DEFAULT_AI_LIMITS)
    if not isinstance(data, dict):
        return DEFAULT_AI_LIMITS
    if "free" not in data:
        data["free"] = 20
    if "premium" not in data:
        data["premium"] = 100
    if "count_cached" not in data:
        data["count_cached"] = False
    return data


async def set_ai_limits(free: int, premium: int, count_cached: bool = None):
    current = await get_ai_limits()
    new = {
        "free": free,
        "premium": premium,
        "count_cached": count_cached if count_cached is not None else current.get("count_cached", False),
    }
    await set_setting("ai_limits", new)


async def get_user_ai_limit(user_id: int) -> int:
    """Возвращает лимит для пользователя (-1 = без лимита)."""
    if await is_admin(user_id):
        return -1  # без лимита

    limits = await get_ai_limits()
    paid = await is_paid(user_id)
    if paid:
        return limits.get("premium", 100)
    return limits.get("free", 20)


async def get_ai_usage(user_id: int) -> int:
    """Сколько запросов сделал пользователь сегодня."""
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT count FROM ai_usage WHERE user_id = $1 AND usage_date = $2",
            user_id, today
        )
    return count or 0


async def increment_ai_usage(user_id: int) -> int:
    """Увеличивает счётчик на 1, возвращает новое значение."""
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ai_usage (user_id, usage_date, count)
            VALUES ($1, $2, 1)
            ON CONFLICT (user_id, usage_date)
            DO UPDATE SET count = ai_usage.count + 1
        """, user_id, today)
        count = await conn.fetchval(
            "SELECT count FROM ai_usage WHERE user_id = $1 AND usage_date = $2",
            user_id, today
        )
    return count or 0


async def reset_all_ai_usage():
    """Сбрасывает счётчики ВСЕМ пользователям."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM ai_usage")


async def get_total_ai_usage_today() -> int:
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COALESCE(SUM(count), 0) FROM ai_usage WHERE usage_date = $1",
            today
        )
    return total or 0


async def get_top_ai_users(limit: int = 5):
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT user_id, count FROM ai_usage
            WHERE usage_date = $1
            ORDER BY count DESC LIMIT $2
        """, today, limit)
        return [dict(r) for r in rows]


# ============================================================
# SETTINGS
# ============================================================
async def get_setting(key: str, default=None):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM settings WHERE key = $1", key)
    if val is None:
        return default
    try:
        return json.loads(val)
    except Exception:
        return val


async def set_setting(key: str, value):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO settings (key, value, updated_at)
            VALUES ($1, $2, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE
            SET value = $2, updated_at = CURRENT_TIMESTAMP
        """, key, json.dumps(value, ensure_ascii=False))


# ============================================================
# PRICING
# ============================================================
async def get_pricing() -> dict:
    data = await get_setting("pricing", DEFAULT_PRICING)
    if not isinstance(data, dict):
        return DEFAULT_PRICING
    return data


async def set_pricing(pricing: dict):
    await set_setting("pricing", pricing)


# ============================================================
# TRIAL
# ============================================================
async def get_trial() -> dict:
    data = await get_setting("trial", DEFAULT_TRIAL)
    if not isinstance(data, dict):
        return DEFAULT_TRIAL
    if "enabled" not in data:
        data["enabled"] = True
    if "days" not in data:
        data["days"] = 1
    return data


async def set_trial(enabled: bool, days: int):
    await set_setting("trial", {"enabled": enabled, "days": days})


# ============================================================
# HOROSCOPE CACHE
# ============================================================
async def get_daily_horoscope(lang: str = "ru"):
    key = f"daily_horoscope_{lang}"
    data = await get_setting(key)
    if not data or not isinstance(data, dict):
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("date") == today:
        return data.get("text")
    return None


async def set_daily_horoscope(text: str, lang: str = "ru"):
    key = f"daily_horoscope_{lang}"
    today = datetime.now().strftime("%Y-%m-%d")
    await set_setting(key, {"date": today, "text": text})


# ============================================================
# COMPATIBILITY CACHE
# ============================================================
async def get_compat_cache(sign1: str, sign2: str):
    key = "compat_" + "_".join(sorted([sign1.lower(), sign2.lower()]))
    return await get_setting(key)


async def set_compat_cache(sign1: str, sign2: str, data: dict):
    key = "compat_" + "_".join(sorted([sign1.lower(), sign2.lower()]))
    await set_setting(key, data)


# ============================================================
# NATAL CACHE
# ============================================================
async def get_natal_cache(cache_key: str):
    return await get_setting(f"natal_{cache_key}")


async def set_natal_cache(cache_key: str, text: str):
    await set_setting(f"natal_{cache_key}", {"text": text})


# ============================================================
# ОЧИСТКА КЭША AI
# ============================================================
async def clean_time_dependent_cache():
    """Удаляет все временные ответы (с _YYYY-MM-DD в ключе)."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("""
            DELETE FROM ai_history
            WHERE request_key ~ '_[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        """)
        return result


async def clean_old_ai_history_v2(days: int = 14):
    """Удаляет записи старше N дней."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            f"DELETE FROM ai_history WHERE created_at < NOW() - INTERVAL '{days} days'"
        )
        return result


async def get_ai_cache_stats() -> dict:
    """Статистика кэша."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM ai_history") or 0
        time_dep = await conn.fetchval("""
            SELECT COUNT(*) FROM ai_history
            WHERE request_key ~ '_[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        """) or 0
        personal = await conn.fetchval("""
            SELECT COUNT(*) FROM ai_history WHERE request_key LIKE 'personal_%'
        """) or 0
        general = await conn.fetchval("""
            SELECT COUNT(*) FROM ai_history WHERE request_key LIKE 'general_%'
        """) or 0
    return {
        "total": total,
        "time_dependent": time_dep,
        "permanent": total - time_dep,
        "personal": personal,
        "general": general,
    }


# ============================================================
# НАПОМИНАНИЯ
# ============================================================
async def get_reminder_settings() -> dict:
    """Настройки напоминаний."""
    default = {"enabled": True, "inactive_months": 1}
    data = await get_setting("reminder_settings", default)
    if not isinstance(data, dict):
        return default
    if "enabled" not in data:
        data["enabled"] = True
    if "inactive_months" not in data:
        data["inactive_months"] = 1
    return data


async def set_reminder_settings(enabled: bool, inactive_months: int = 1):
    await set_setting("reminder_settings", {
        "enabled": enabled,
        "inactive_months": inactive_months,
    })


async def get_users_for_reminder(limit: int = 100) -> list:
    """
    Возвращает пользователей, которым нужно напомнить о профиле.
    Условия:
    - profile_completed = FALSE
    - последнее напоминание > 7 дней назад (или не было)
    - последняя активность < N месяцев назад
    """
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT u.user_id
            FROM users u
            LEFT JOIN settings s ON s.key = 'reminder_' || u.user_id::text
            WHERE
                u.profile_completed = FALSE
                AND (
                    s.value IS NULL
                    OR (s.value::jsonb->>'last_reminder')::timestamp < NOW() - INTERVAL '7 days'
                )
                AND u.created_at > NOW() - INTERVAL '1 month' * $1
            ORDER BY u.created_at DESC
            LIMIT $2
        """, 1, limit)
        return [dict(r) for r in rows]


async def set_last_reminder(user_id: int):
    """Записывает, когда последний раз отправляли напоминание."""
    from datetime import datetime as dt
    key = f"reminder_{user_id}"
    await set_setting(key, {
        "last_reminder": dt.now().isoformat(),
    })


async def should_send_reminder(user_id: int) -> bool:
    """Проверяет, можно ли отправить напоминание."""
    key = f"reminder_{user_id}"
    data = await get_setting(key)
    if not data or not isinstance(data, dict):
        return True
    last = data.get("last_reminder")
    if not last:
        return True
    try:
        from datetime import datetime as dt, timedelta
        last_dt = dt.fromisoformat(last)
        return (dt.now() - last_dt) > timedelta(days=7)
    except Exception:
        return True


# ============================================================
# АВТООЧИСТКА КЭША
# ============================================================
async def auto_clean_cache():
    """
    Автоматическая очистка кэша:
    - Временные > 7 дней
    - Постоянные > 90 дней
    """
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        # Временные (с датой в ключе)
        r1 = await conn.execute("""
            DELETE FROM ai_history
            WHERE request_key ~ '_[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            AND created_at < NOW() - INTERVAL '7 days'
        """)
        # Постоянные (без даты)
        r2 = await conn.execute("""
            DELETE FROM ai_history
            WHERE request_key !~ '_[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            AND created_at < NOW() - INTERVAL '90 days'
        """)
    logger.info(f"🧹 Автоочистка кэша: временные={r1}, постоянные={r2}")
    return {"temporary": r1, "permanent": r2}


async def get_cache_cleanup_settings() -> dict:
    default = {"enabled": True}
    data = await get_setting("cache_cleanup", default)
    if not isinstance(data, dict):
        return default
    if "enabled" not in data:
        data["enabled"] = True
    return data


async def set_cache_cleanup_settings(enabled: bool):
    await set_setting("cache_cleanup", {"enabled": enabled})


# ============================================================
# РЕФЕРАЛЬНАЯ ПРОГРАММА
# ============================================================
async def init_referrals_table():
    """Создаёт таблицу referrals."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referral_id BIGINT UNIQUE NOT NULL,
                bonus_days INTEGER DEFAULT 3,
                bonus_given BOOLEAN DEFAULT FALSE,
                bonus_paid BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_referrals_referrer
            ON referrals(referrer_id)
        """)
    logger.info("✅ Таблица referrals создана/проверена")


async def get_referral_settings() -> dict:
    default = {
        "enabled": True,
        "bonus_days": 3,
        "max_bonuses": 10,
    }
    data = await get_setting("referral_settings", default)
    if not isinstance(data, dict):
        return default
    for k, v in default.items():
        if k not in data:
            data[k] = v
    return data


async def set_referral_settings(enabled: bool = None, bonus_days: int = None,
                                 max_bonuses: int = None):
    current = await get_referral_settings()
    if enabled is not None:
        current["enabled"] = enabled
    if bonus_days is not None:
        current["bonus_days"] = bonus_days
    if max_bonuses is not None:
        current["max_bonuses"] = max_bonuses
    await set_setting("referral_settings", current)


async def add_referral(referrer_id: int, referral_id: int, bonus_days: int = 3) -> bool:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM referrals WHERE referral_id = $1", referral_id
        )
        if existing:
            return False
        await conn.execute("""
            INSERT INTO referrals (referrer_id, referral_id, bonus_days)
            VALUES ($1, $2, $3)
        """, referrer_id, referral_id, bonus_days)
        return True


async def mark_referral_bonus_paid(referral_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE referrals SET bonus_given = TRUE, bonus_paid = TRUE
            WHERE referral_id = $1
        """, referral_id)


async def count_user_referrals(referrer_id: int) -> int:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1",
            referrer_id
        )
    return count or 0


async def count_user_referrals_with_bonus(referrer_id: int) -> int:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = $1 AND bonus_given = TRUE",
            referrer_id
        )
    return count or 0


# ============================================================
# УТРЕННИЕ ФАКТЫ
# ============================================================
async def get_daily_fact_settings() -> dict:
    default = {"enabled": True, "hour_utc": 9, "minute_utc": 0}
    data = await get_setting("daily_fact_settings", default)
    if not isinstance(data, dict):
        return default
    for k, v in default.items():
        if k not in data:
            data[k] = v
    return data


async def set_daily_fact_settings(enabled: bool = None, hour_utc: int = None,
                                   minute_utc: int = None):
    current = await get_daily_fact_settings()
    if enabled is not None:
        current["enabled"] = enabled
    if hour_utc is not None:
        current["hour_utc"] = hour_utc
    if minute_utc is not None:
        current["minute_utc"] = minute_utc
    await set_setting("daily_fact_settings", current)


async def get_today_fact(lang: str = "ru") -> dict:
    from datetime import datetime as dt
    today = dt.now().strftime("%Y-%m-%d")
    data = await get_setting(f"daily_fact_{lang}", {})
    if not isinstance(data, dict):
        return {}
    if data.get("date") == today:
        return data
    return {}


async def set_today_fact(text: str, lang: str = "ru"):
    from datetime import datetime as dt
    today = dt.now().strftime("%Y-%m-%d")
    await set_setting(f"daily_fact_{lang}", {"date": today, "text": text})


async def save_fact_history(text: str):
    from datetime import datetime as dt
    history = await get_setting("daily_fact_history", [])
    if not isinstance(history, list):
        history = []
    history.insert(0, {
        "date": dt.now().strftime("%Y-%m-%d"),
        "text": text,
    })
    history = history[:7]
    await set_setting("daily_fact_history", history)


async def get_fact_history() -> list:
    history = await get_setting("daily_fact_history", [])
    if not isinstance(history, list):
        return []
    return history


async def get_all_users() -> list:
    """Все пользователи."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [dict(r) for r in rows]


async def count_all_users() -> int:
    """Общее число пользователей."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM users")
    return count or 0


# ============================================================
# УПРАВЛЕНИЕ АДМИНАМИ
# ============================================================
async def get_extra_admins() -> list:
    data = await get_setting("extra_admins", [])
    if not isinstance(data, list):
        return []
    result = []
    for x in data:
        try:
            result.append(int(x))
        except (ValueError, TypeError):
            pass
    return result


async def add_extra_admin(user_id: int) -> bool:
    current = await get_extra_admins()
    if user_id in current:
        return False
    current.append(int(user_id))
    await set_setting("extra_admins", current)
    return True


async def remove_extra_admin(user_id: int) -> bool:
    current = await get_extra_admins()
    if user_id not in current:
        return False
    current.remove(int(user_id))
    await set_setting("extra_admins", current)
    return True


async def get_all_admins() -> list:
    from config import ADMINS as MAIN_ADMINS
    extra = await get_extra_admins()
    return list(set(MAIN_ADMINS + extra))


async def is_admin(user_id: int) -> bool:
    from config import ADMINS as MAIN_ADMINS
    if user_id in MAIN_ADMINS:
        return True
    # Кэш
    try:
        from services.cache import admin_cache
        cached = admin_cache.get(f"adm_{user_id}")
        if cached is not None:
            return cached
    except Exception:
        pass
    extra = await get_extra_admins()
    result = user_id in extra
    try:
        from services.cache import admin_cache
        admin_cache.set(f"adm_{user_id}", result, ttl=60)
    except Exception:
        pass
    return result


async def is_main_admin(user_id: int) -> bool:
    from config import ADMINS as MAIN_ADMINS
    return user_id in MAIN_ADMINS


# ============================================================
# АВТОУДАЛЕНИЕ МЕНЮ
# ============================================================
async def set_last_menu(user_id: int, message_id: int, chat_id: int):
    """Сохраняет ID последнего меню-сообщения."""
    key = f"last_menu_{user_id}"
    await set_setting(key, {
        "message_id": message_id,
        "chat_id": chat_id,
    })


async def get_last_menu(user_id: int):
    """Возвращает (chat_id, message_id) последнего меню."""
    key = f"last_menu_{user_id}"
    data = await get_setting(key)
    if not data or not isinstance(data, dict):
        return None
    mid = data.get("message_id")
    cid = data.get("chat_id")
    if mid and cid:
        return cid, mid
    return None


async def clear_last_menu(user_id: int):
    """Очищает запись о последнем меню."""
    key = f"last_menu_{user_id}"
    try:
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM settings WHERE key = $1", key
            )
    except Exception as e:
        logger.warning(f"clear_last_menu: {e}")


# ============================================================
# LAST MENUS (v2) — 2 ID: факт + inline
# ============================================================
async def set_last_menus(user_id: int, chat_id: int, fact_id: int = None, inline_id: int = None):
    """Сохраняет ID последних меню-сообщений."""
    key = f"last_menus_{user_id}"
    current = await get_setting(key, {}) or {}
    # Собираем список extras (предыдущие ID)
    extras = current.get("extras", [])
    for old_id in (current.get("fact_id"), current.get("inline_id")):
        if old_id and old_id not in extras:
            extras.append(old_id)
    # Ограничиваем 10
    extras = extras[-10:]

    if fact_id is not None:
        current["fact_id"] = fact_id
    if inline_id is not None:
        current["inline_id"] = inline_id
    current["chat_id"] = chat_id
    current["extras"] = extras
    await set_setting(key, current)


async def get_last_menus(user_id: int):
    """Возвращает dict с chat_id, fact_id, inline_id."""
    key = f"last_menus_{user_id}"
    data = await get_setting(key, {})
    if not isinstance(data, dict):
        return {}
    return data


async def clear_last_menus(user_id: int):
    """Очищает записи."""
    key = f"last_menus_{user_id}"
    try:
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM settings WHERE key = $1", key)
    except Exception as e:
        logger.warning(f"clear_last_menus: {e}")


# ============================================================
# ИНВАЛИДАЦИЯ КЭША
# ============================================================
def invalidate_user_cache(user_id: int):
    """Сбрасывает кэш пользователя (при обновлении профиля)."""
    try:
        from services.cache import user_cache, paid_cache, admin_cache
        user_cache.delete(f"user_{user_id}")
        paid_cache.delete(f"paid_{user_id}")
        admin_cache.delete(f"adm_{user_id}")
    except Exception:
        pass


# ============================================================
# ДНЕВНИК НАСТРОЕНИЯ
# ============================================================
async def init_mood_table():
    """Создаёт таблицу mood_diary."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mood_diary (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                mood INTEGER NOT NULL,
                mood_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, mood_date)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mood_user ON mood_diary(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mood_date ON mood_diary(mood_date)
        """)
    logger.info("✅ Таблица mood_diary создана/проверена")


async def set_mood(user_id: int, mood: int):
    """Сохраняет настроение на сегодня (или обновляет)."""
    from datetime import date
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mood_diary (user_id, mood, mood_date)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, mood_date)
            DO UPDATE SET mood = $2, created_at = CURRENT_TIMESTAMP
        """, user_id, mood, today)


async def get_mood_today(user_id: int):
    """Возвращает настроение за сегодня или None."""
    from datetime import date
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mood FROM mood_diary WHERE user_id = $1 AND mood_date = $2",
            user_id, today
        )
        return row["mood"] if row else None


async def get_mood_history(user_id: int, days: int = 30) -> list:
    """Возвращает список настроений за N дней (от новых к старым)."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT mood, mood_date FROM mood_diary
            WHERE user_id = $1
              AND mood_date >= CURRENT_DATE - INTERVAL '{days} days'
            ORDER BY mood_date DESC
        """, user_id)
        return [dict(r) for r in rows]


async def get_mood_stats(user_id: int, days: int = 7) -> dict:
    """Статистика: средний балл, количество записей."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(f"""
            SELECT
                COUNT(*) as total,
                AVG(mood) as avg_mood,
                MIN(mood) as min_mood,
                MAX(mood) as max_mood
            FROM mood_diary
            WHERE user_id = $1
              AND mood_date >= CURRENT_DATE - INTERVAL '{days} days'
        """, user_id)
        return {
            "total": row["total"] or 0,
            "avg": float(row["avg_mood"]) if row["avg_mood"] else 0,
            "min": row["min_mood"] or 0,
            "max": row["max_mood"] or 0,
        }


async def count_bad_mood_streak(user_id: int) -> int:
    """Считает подряд идущие дни с плохим настроением (<=2)."""
    history = await get_mood_history(user_id, days=10)
    streak = 0
    for entry in history:
        if entry["mood"] <= 2:
            streak += 1
        else:
            break
    return streak


# ============================================================
# РЕКЛАМА
# ============================================================
async def init_ads_tables():
    """Создаёт таблицы ads и ad_stats."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                link TEXT,
                button_text TEXT DEFAULT 'Подробнее',
                utm_source TEXT DEFAULT 'astro_bot',
                utm_medium TEXT DEFAULT 'ad',
                enabled BOOLEAN DEFAULT TRUE,
                weight INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ad_stats (
                id SERIAL PRIMARY KEY,
                ad_id INTEGER REFERENCES ads(id) ON DELETE CASCADE,
                user_id BIGINT,
                action TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ad_stats_ad ON ad_stats(ad_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ad_stats_date ON ad_stats(created_at)
        """)
    logger.info("✅ Таблицы ads/ad_stats созданы/проверены")


async def get_ads_config() -> dict:
    default = {
        "enabled": False,
        "place": "menu",
        "frequency": "daily",
        "frequency_value": 1,
        "max_per_day": 3,
        "show_to_admins": False,
    }
    data = await get_setting("ads_config", default)
    if not isinstance(data, dict):
        return default
    for k, v in default.items():
        if k not in data:
            data[k] = v
    return data


async def set_ads_config(**kwargs):
    current = await get_ads_config()
    for k, v in kwargs.items():
        current[k] = v
    await set_setting("ads_config", current)


async def get_all_ads(only_enabled: bool = False) -> list:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        if only_enabled:
            rows = await conn.fetch(
                "SELECT * FROM ads WHERE enabled = TRUE ORDER BY id"
            )
        else:
            rows = await conn.fetch("SELECT * FROM ads ORDER BY id")
        return [dict(r) for r in rows]


async def get_ad(ad_id: int):
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM ads WHERE id = $1", ad_id)
        return dict(row) if row else None


async def add_ad(text: str, link: str = None, button_text: str = "Подробнее",
                  utm_source: str = "astro_bot", utm_medium: str = "ad") -> int:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO ads (text, link, button_text, utm_source, utm_medium)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """, text, link, button_text, utm_source, utm_medium)
        return row["id"]


async def update_ad(ad_id: int, **kwargs) -> bool:
    allowed = {"text", "link", "button_text", "enabled", "weight",
               "utm_source", "utm_medium"}
    fields = []
    values = []
    for i, (k, v) in enumerate(kwargs.items(), 1):
        if k not in allowed:
            continue
        fields.append(f"{k} = ${i}")
        values.append(v)
    if not fields:
        return False
    values.append(ad_id)
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE ads SET {', '.join(fields)} WHERE id = ${len(values)}",
            *values
        )
    return True


async def delete_ad(ad_id: int) -> bool:
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM ads WHERE id = $1", ad_id)
    return result.endswith("1")


async def toggle_ad(ad_id: int) -> bool:
    """Переключает enabled. Возвращает новое состояние."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE ads SET enabled = NOT enabled WHERE id = $1 RETURNING enabled",
            ad_id
        )
        return row["enabled"] if row else False


async def log_ad_action(ad_id: int, user_id: int, action: str):
    """Логирует показ или клик."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO ad_stats (ad_id, user_id, action)
            VALUES ($1, $2, $3)
        """, ad_id, user_id, action)


async def get_ad_stats(ad_id: int, days: int = 7) -> dict:
    """Статистика одного блока за N дней."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        shows = await conn.fetchval(f"""
            SELECT COUNT(*) FROM ad_stats
            WHERE ad_id = $1 AND action = 'show'
            AND created_at >= NOW() - INTERVAL '{days} days'
        """, ad_id) or 0
        clicks = await conn.fetchval(f"""
            SELECT COUNT(*) FROM ad_stats
            WHERE ad_id = $1 AND action = 'click'
            AND created_at >= NOW() - INTERVAL '{days} days'
        """, ad_id) or 0
    ctr = (clicks / shows * 100) if shows > 0 else 0
    return {"shows": shows, "clicks": clicks, "ctr": round(ctr, 1)}


async def get_all_ad_stats(days: int = 7) -> dict:
    """Общая статистика за N дней."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        shows = await conn.fetchval(f"""
            SELECT COUNT(*) FROM ad_stats
            WHERE action = 'show'
            AND created_at >= NOW() - INTERVAL '{days} days'
        """) or 0
        clicks = await conn.fetchval(f"""
            SELECT COUNT(*) FROM ad_stats
            WHERE action = 'click'
            AND created_at >= NOW() - INTERVAL '{days} days'
        """) or 0
    ctr = (clicks / shows * 100) if shows > 0 else 0
    return {"shows": shows, "clicks": clicks, "ctr": round(ctr, 1)}


async def should_show_ad(user_id: int) -> bool:
    """Проверяет, показывать ли рекламу пользователю сейчас."""
    config = await get_ads_config()
    if not config.get("enabled"):
        return False

    # Админам?
    if not config.get("show_to_admins", False):
        if await is_admin(user_id):
            return False

    # Лимит в день
    from datetime import date
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        today_count = await conn.fetchval("""
            SELECT COUNT(*) FROM ad_stats
            WHERE user_id = $1
            AND action = 'show'
            AND created_at::date = CURRENT_DATE
        """, user_id) or 0

    max_per_day = config.get("max_per_day", 3)
    if max_per_day > 0 and today_count >= max_per_day:
        return False

    # Частота
    freq = config.get("frequency", "daily")
    if freq == "always":
        return True
    elif freq == "daily":
        # Уже показывали сегодня?
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            shown_today = await conn.fetchval("""
                SELECT COUNT(*) FROM ad_stats
                WHERE user_id = $1
                AND action = 'show'
                AND created_at::date = CURRENT_DATE
            """, user_id) or 0
        return shown_today == 0
    elif freq == "every_n":
        n = config.get("frequency_value", 5)
        if n <= 0:
            return True
        # Считаем все действия пользователя (можно заменить на счётчик меню)
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM requests WHERE user_id = $1
            """, user_id) or 0
        return (total % n) == 0
    return True


async def pick_random_ad() -> dict:
    """Случайный активный рекламный блок."""
    ads = await get_all_ads(only_enabled=True)
    if not ads:
        return {}
    import random
    # Взвешенный выбор
    weights = [max(1, a.get("weight", 1)) for a in ads]
    return random.choices(ads, weights=weights, k=1)[0]


# ============================================================
# MIGRATION: link_mode для ads
# ============================================================
async def migrate_ads_link_mode():
    """Добавляет поле link_mode в ads, если его нет."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                "ALTER TABLE ads ADD COLUMN IF NOT EXISTS link_mode TEXT DEFAULT 'direct'"
            )
        except Exception as e:
            logger.warning(f"migrate_ads_link_mode: {e}")


# ============================================================
# СТАТИСТИКА ПО ТАРИФАМ
# ============================================================
async def get_tariff_stats() -> dict:
    """
    Возвращает разбивку пользователей по тарифам.
    - free: ни разу не платили
    - trial: на триале (is_paid=TRUE, но нет платежей)
    - 7d/30d/90d: последний платёж был на этот срок
    - admins: админы
    """
    from config import ADMINS as MAIN_ADMINS
    extra = await get_extra_admins()
    all_admins = set(MAIN_ADMINS + extra)

    pool = await db.create_pool()
    async with pool.acquire() as conn:
        # Все пользователи
        rows = await conn.fetch("""
            SELECT 
                user_id,
                is_paid,
                subscription_end,
                (SELECT days FROM payments 
                 WHERE user_id = users.user_id 
                 ORDER BY created_at DESC LIMIT 1) as last_days,
                (SELECT COUNT(*) FROM payments 
                 WHERE user_id = users.user_id) as pay_count
            FROM users
        """)

    result = {
        "total": len(rows),
        "admins": 0,
        "free": 0,
        "trial": 0,
        "7d": 0,
        "30d": 0,
        "90d": 0,
        "other": 0,
    }

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")

    for r in rows:
        uid = r["user_id"]
        if uid in all_admins:
            result["admins"] += 1
            continue

        if not r["is_paid"]:
            result["free"] += 1
            continue

        # Подписка активна?
        sub_end = r["subscription_end"]
        if sub_end and sub_end < today:
            result["free"] += 1
            continue

        # Есть ли платежи?
        if r["pay_count"] == 0:
            result["trial"] += 1
            continue

        last_days = r["last_days"] or 0
        if last_days == 7:
            result["7d"] += 1
        elif last_days == 30:
            result["30d"] += 1
        elif last_days == 90:
            result["90d"] += 1
        else:
            result["other"] += 1

    return result


# ============================================================
# ТАРО — КЭШ РАСКЛАДОВ
# ============================================================
async def init_tarot_table():
    """Создаёт таблицу tarot_readings."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tarot_readings (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                question TEXT NOT NULL,
                cache_key TEXT NOT NULL,
                reading_date DATE NOT NULL,
                cards JSONB NOT NULL,
                ai_answer TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cache_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tarot_user ON tarot_readings(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tarot_date ON tarot_readings(reading_date)
        """)
    logger.info("✅ Таблица tarot_readings создана/проверена")


async def get_tarot_reading(cache_key: str):
    """Возвращает расклад по ключу кэша или None."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT cards, ai_answer, reading_date
            FROM tarot_readings
            WHERE cache_key = $1
        """, cache_key)
        return dict(row) if row else None


async def save_tarot_reading(user_id: int, question: str, cache_key: str,
                              cards: list, ai_answer: str):
    """Сохраняет расклад в БД."""
    import json
    from datetime import date
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tarot_readings (user_id, question, cache_key, reading_date, cards, ai_answer)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (cache_key) DO NOTHING
        """, user_id, question, cache_key, today, json.dumps(cards, ensure_ascii=False), ai_answer)


async def count_tarot_today() -> int:
    """Сколько раскладов сделано сегодня."""
    from datetime import date
    today = date.today()
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM tarot_readings WHERE reading_date = $1", today
        )
    return count or 0

# ============================================================
# МУЛЬТИЯЗЫЧНОСТЬ
# ============================================================
async def update_user_language(user_id: int, lang: str):
    """Сохраняет язык пользователя и сбрасывает оба кэша."""
    pool = await db.create_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET language = $1 WHERE user_id = $2",
            lang, user_id
        )
    # Инвалидация кэшей
    try:
        _lang_cache.pop(user_id, None)
    except Exception:
        pass
    try:
        from services.cache import user_cache
        user_cache.delete(f"user_{user_id}")
    except Exception:
        pass


async def get_user_language(user_id: int) -> str:
    """Возвращает язык пользователя (или 'ru')."""
    try:
        pool = await db.create_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval(
                "SELECT language FROM users WHERE user_id = $1",
                user_id
            )
        return val or "ru"
    except Exception:
        return "ru"

# ============================================================
# КЭШ ЯЗЫКА (in-memory, TTL 5 мин)
# ============================================================
_lang_cache: dict = {}


async def get_user_lang_cached(user_id: int) -> str:
    """Возвращает язык пользователя с кэшем 5 минут."""
    import time
    now = time.time()
    entry = _lang_cache.get(user_id)
    if entry and entry[1] > now:
        return entry[0]
    lang = await get_user_language(user_id)
    _lang_cache[user_id] = (lang, now + 300)
    return lang


def invalidate_lang_cache(user_id: int):
    """Сбрасывает кэш языка пользователя."""
    _lang_cache.pop(user_id, None)
