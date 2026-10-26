import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()


async def safe_edit(msg, text, reply_markup=None):
    try:
        if reply_markup:
            await msg.edit_text(text, reply_markup=reply_markup)
        else:
            await msg.edit_text(text)
    except Exception as e:
        if "message is not modified" in str(e):
            return
        try:
            if reply_markup:
                await msg.answer(text, reply_markup=reply_markup)
            else:
                await msg.answer(text)
        except Exception:
            pass


def help_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Анализ", callback_data="help_analysis")],
        [InlineKeyboardButton(text="📚 Библиотека", callback_data="help_books")],
        [InlineKeyboardButton(text="📈 Стратегии", callback_data="help_strategies")],
        [InlineKeyboardButton(text="💼 Торговля", callback_data="help_trading")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="help_settings")],
        [InlineKeyboardButton(text="Меню", callback_data="back_to_menu")],
    ])


@router.callback_query(F.data == "stub_help")
async def help_menu(callback: CallbackQuery):
    text = (
        "ПОМОЩЬ\n\n"
        "Этот бот — инструмент для анализа графиков и автоматизации торговли.\n\n"
        "Что он делает:\n"
        "• Принимает фото графика → AI распознаёт тикер, тренд, паттерны → даёт прогноз\n"
        "• Загружает книги (PDF/DOCX) → AI использует их при анализе\n"
        "• Позволяет создавать стратегии и прогонять бэктест на истории\n"
        "• Открывает сделки на testnet (демо) с проверкой рисков\n\n"
        "Выбери раздел, чтобы узнать подробнее:"
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()


@router.callback_query(F.data == "help_analysis")
async def help_analysis(callback: CallbackQuery):
    text = (
        "АНАЛИЗ ГРАФИКОВ\n\n"
        "Как работает:\n"
        "1. Отправь фото графика (скриншот с TradingView, Binance и т.д.)\n"
        "2. AI распознаёт: тикер, таймфрейм, тренд, уровни, паттерны, свечи, индикаторы, объёмы\n"
        "3. Если данных мало — AI задаст 2-3 вопроса (например, какой таймфрейм)\n"
        "4. После ответа — даёт прогноз с обоснованием\n\n"
        "Что в ответе:\n"
        "• Тикер, таймфрейм, цена, тренд\n"
        "• Ключевые уровни (поддержка/сопротивление)\n"
        "• Паттерны и свечи\n"
        "• Прогноз: направление, уверенность, 5-8 пунктов обоснования\n"
        "• Сценарии (что для роста, что для падения)\n"
        "• Цели, отмена прогноза, риски\n\n"
        "Кнопка «📖 Подробнее» — показывает всё, что AI увидел на графике.\n\n"
        "Если загружены книги в Библиотеке — AI учтёт их правила и паттерны."
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()


@router.callback_query(F.data == "help_books")
async def help_books(callback: CallbackQuery):
    text = (
        "БИБЛИОТЕКА\n\n"
        "Зачем нужна:\n"
        "AI не «знает» все книги по трейдингу. Ты загружаешь свои — и AI использует их при анализе графиков.\n\n"
        "Как загрузить:\n"
        "1. Нажми «📤 Загрузить книгу»\n"
        "2. Отправь PDF или DOCX (до 10 МБ)\n"
        "3. Подожди 2-5 минут — AI делает конспект (по главам + общий)\n"
        "4. Готово — теперь книга используется в анализе\n\n"
        "Что происходит при загрузке:\n"
        "• Текст режется на чанки по 500 символов → RAG-поиск\n"
        "• Главы суммируются → общий конспект (правила, паттерны, входы, выходы)\n\n"
        "Как AI использует книги:\n"
        "• При анализе графика получает конспекты ВСЕХ книг\n"
        "• Ищет релевантные выдержки (RAG)\n"
        "• Указывает источники в прогнозе\n\n"
        "Сколько книг можно: 10-50 (без ограничений в коде)."
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()


@router.callback_query(F.data == "help_strategies")
async def help_strategies(callback: CallbackQuery):
    text = (
        "СТРАТЕГИИ\n\n"
        "Что это:\n"
        "Набор правил: индикаторы + условия входа + условия выхода + риск.\n\n"
        "Как создать:\n"
        "1. «+ Создать из пресета» — выбери готовую (RSI-реверсия, EMA-кроссовер, Bollinger)\n"
        "2. Введи тикер (BTC/USDT)\n"
        "3. Стратегия появится в списке\n\n"
        "Что можно делать:\n"
        "• Включить/выключить\n"
        "• Прогнать бэктест на истории (1000 свечей)\n"
        "• Посмотреть метрики: доходность, просадка, win rate, profit factor, сделки\n"
        "• Удалить\n\n"
        "Бэктест — это НЕ гарантия. Результат на истории ≠ результат в будущем.\n"
        "Возможен overfitting (переобучение)."
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()


@router.callback_query(F.data == "help_trading")
async def help_trading(callback: CallbackQuery):
    text = (
        "ТОРГОВЛЯ\n\n"
        "ВАЖНО: сейчас только DEMO (testnet). Реальные деньги не используются.\n\n"
        "Как открыть сделку:\n"
        "1. Торговля → Открыть сделку\n"
        "2. Введи тикер (BTCUSDT)\n"
        "3. Выбери LONG/SHORT\n"
        "4. Введи размер (0.001)\n"
        "5. Введи плечо (1-10)\n"
        "6. Введи SL и TP через пробел (60000 65000)\n"
        "7. RiskGuard проверит — покажет уровень риска\n"
        "8. Подтверди → ордер уйдёт на testnet\n\n"
        "RiskGuard проверяет:\n"
        "• Плечо (не больше твоего лимита)\n"
        "• Риск (не больше лимита)\n"
        "• Размер позиции (не больше лимита депозита)\n"
        "• Наличие SL и TP (оба обязательны)\n\n"
        "Уровни риска:\n"
        "• Низкий (плечо ≤3x, риск ≤2%) — откроется сразу\n"
        "• Средний (3-5x, 2-5%) — предупреждение + подтверждение\n"
        "• Высокий (5-10x, 5-10%) — двойное предупреждение\n"
        "• Критический (>10x, нет SL/TP) — блокировка"
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()


@router.callback_query(F.data == "help_settings")
async def help_settings(callback: CallbackQuery):
    text = (
        "НАСТРОЙКИ\n\n"
        "Мой профиль:\n"
        "• ID, имя, username\n"
        "• Лимиты (плечо, риск, депозит, убыток/день, сделок/день)\n"
        "• Спот/фьючерсы\n"
        "• Активность (стратегии, бэктесты)\n\n"
        "Мои стратегии:\n"
        "• Список всех твоих стратегий\n"
        "• Статус (активна/выкл)\n\n"
        "История бэктестов:\n"
        "• Последние 10 прогонов\n"
        "• Доходность, просадка, win rate, сделки\n\n"
        "Лимиты меняет только админ. Если нужно поднять — попроси админа."
    )
    await safe_edit(callback.message, text, reply_markup=help_kb())
    await callback.answer()