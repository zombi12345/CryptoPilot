from database.db import (
    get_pool, close_pool, init_db, init_payments_db, init_trader_db, init_portfolio_db, init_daily_bonus_db, init_shop_db, init_referral_db, init_trade_mode_db, init_ai_limits_db,
    create_user_if_missing, set_agreed, get_user,
    list_strategies, get_strategy, create_strategy, toggle_strategy, delete_strategy,
    save_backtest, list_backtests,
    save_book_summary, get_book_summary, get_all_book_summaries, delete_book_summary,
    get_global_setting, set_global_setting, get_all_global_settings,
    unban_all, ban_all_non_admins,
    add_exchange_key, get_exchange_keys, list_exchange_keys, delete_exchange_key,
    save_order, close_order_in_db, list_orders, get_orders_stats,
    toggle_auto_trade, get_auto_trade_users, get_daily_pnl,
    get_auto_settings, update_auto_settings,
    check_and_increment_ai,
)

__all__ = [
    "get_pool", "close_pool", "init_db", "init_payments_db", "init_trader_db", "init_portfolio_db", "init_daily_bonus_db", "init_shop_db", "init_referral_db", "init_trade_mode_db", "init_ai_limits_db",
    "create_user_if_missing", "set_agreed", "get_user",
    "list_strategies", "get_strategy", "create_strategy", "toggle_strategy", "delete_strategy",
    "save_backtest", "list_backtests",
    "save_book_summary", "get_book_summary", "get_all_book_summaries", "delete_book_summary",
    "get_global_setting", "set_global_setting", "get_all_global_settings",
    "unban_all", "ban_all_non_admins",
    "add_exchange_key", "get_exchange_keys", "list_exchange_keys", "delete_exchange_key",
    "save_order", "close_order_in_db", "list_orders", "get_orders_stats",
    "toggle_auto_trade", "get_auto_trade_users", "get_daily_pnl",
    "get_auto_settings", "update_auto_settings",
    "check_and_increment_ai",
]