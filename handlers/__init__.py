from handlers.start import router as start_router
from handlers.menu import router as menu_router
from handlers.analysis import router as analysis_router
from handlers.books import router as books_router
from handlers.strategies import router as strategies_router
from handlers.stubs import router as stubs_router

__all__ = ["start_router", "menu_router", "analysis_router", "books_router", "strategies_router", "stubs_router"]