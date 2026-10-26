import asyncio
from database import get_pool, init_db

async def main():
    await init_db()
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1. Колонки в payments
        cols = await conn.fetch("""
            SELECT column_name, data_type FROM information_schema.columns 
            WHERE table_name = 'payments'
        """)
        print("1. Колонки в payments:")
        for c in cols:
            print(f"   - {c['column_name']} ({c['data_type']})")
            
        # 2. Последние 5 платежей
        rows = await conn.fetch("SELECT * FROM payments ORDER BY created_at DESC LIMIT 5")
        print(f"\n2. Последние 5 платежей (всего записей: {len(rows)}):")
        for r in rows:
            print(f"   - user_id={r['user_id']}, stars={r['stars_paid']}, days={r['days']}, id={r['payment_id']}")
            
        # 3. Юзеры, которые платили, но is_paid=False
        bad = await conn.fetch("""
            SELECT u.user_id, u.is_paid, u.subscription_end FROM users u
            WHERE EXISTS (SELECT 1 FROM payments p WHERE p.user_id = u.user_id)
              AND u.is_paid = FALSE
        """)
        print(f"\n3. Оплатили, но подписка не активна: {len(bad)}")
        for b in bad:
            print(f"   - user_id={b['user_id']}, sub_end={b['subscription_end']}")

if __name__ == "__main__":
    asyncio.run(main())