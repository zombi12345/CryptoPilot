from aiogram.fsm.state import StatesGroup, State


class StartStates(StatesGroup):
    waiting_agree = State()


class AnalysisStates(StatesGroup):
    waiting_photo = State()
    waiting_ticker = State()


class StrategyStates(StatesGroup):
    waiting_name = State()
    waiting_ticker = State()
    choosing_indicators = State()
    building_entry_rules = State()
    building_exit_rules = State()
    setting_risk = State()


class TradeStates(StatesGroup):
    choosing_symbol = State()
    choosing_direction = State()
    choosing_size = State()
    setting_sl_tp = State()
    confirming = State()


class ApiKeyStates(StatesGroup):
    choosing_exchange = State()
    choosing_mode = State()
    entering_api_key = State()
    entering_secret = State()
    confirming = State()


class AdminStates(StatesGroup):
    waiting_user_id = State()
    waiting_broadcast = State()
    editing_limit = State()


class BooksStates(StatesGroup):
    waiting_file = State()
    waiting_question = State()