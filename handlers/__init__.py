from handlers.start import router as start_router
from handlers.menu import router as menu_router
from handlers.analysis import router as analysis_router
from handlers.books import router as books_router
from handlers.strategies import router as strategies_router
from handlers.api_keys import router as api_keys_router
from handlers.trading import router as trading_router
from handlers.news import router as news_router
from handlers.payment import router as payment_router
from handlers.admin import router as admin_router
from handlers.ads_display import router as ads_display_router
from handlers.journal import router as journal_router
from handlers.portfolio import router as portfolio_router
from handlers.bonus import router as bonus_router
from handlers.shop import router as shop_router
from handlers.referral import router as referral_router
from handlers.settings import router as settings_router
from handlers.help import router as help_router
from handlers.stubs import router as stubs_router

__all__ = [
    "start_router", "menu_router", "analysis_router", "books_router",
    "strategies_router", "api_keys_router", "trading_router", "news_router",
    "payment_router", "admin_router", "ads_display_router", "journal_router",
    "portfolio_router", "bonus_router", "shop_router", "referral_router",
    "settings_router", "help_router", "stubs_router",
]