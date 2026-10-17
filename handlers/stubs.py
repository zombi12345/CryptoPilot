from aiogram import Router, F
from aiogram.types import CallbackQuery
from keyboards.main import main_menu_keyboard
from config import ADMINS

router = Router()


@router.callback_query(F.data == "stub_analysis")
async def stub_analysis(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел Анализ.\n\n"
        "Скоро здесь будет:\n"
        "- Отправка фото графика\n"
        "- AI-анализ\n"
        "- Прогноз направления\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await callback.answer()


@router.callback_query(F.data == "stub_strategies")
async def stub_strategies(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел Стратегии.\n\n"
        "Скоро здесь будет:\n"
        "- Пресеты\n"
        "- Конструктор правил\n"
        "- AI-генератор\n"
        "- Бэктест\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await callback.answer()


@router.callback_query(F.data == "stub_trading")
async def stub_trading(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел Торговля.\n\n"
        "Скоро здесь будет:\n"
        "- Портфель\n"
        "- Открытие сделок\n"
        "- Автоторговля\n"
        "- История\n"
        "- API-ключи\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await callback.answer()


@router.callback_query(F.data == "stub_settings")
async def stub_settings(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел Настройки.\n\n"
        "Скоро здесь будет:\n"
        "- Настройки анализа\n"
        "- Настройки AI\n"
        "- Риск-менеджмент\n"
        "- Уведомления\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await callback.answer()


@router.callback_query(F.data == "stub_help")
async def stub_help(callback: CallbackQuery):
    await callback.message.edit_text(
        "Раздел Помощь.\n\n"
        "Скоро здесь будет:\n"
        "- Как пользоваться\n"
        "- FAQ\n"
        "- Глоссарий\n"
        "- Дисклеймер\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, callback.from_user.id in ADMINS),
    )
    await callback.answer()


@router.callback_query(F.data == "stub_admin")
async def stub_admin(callback: CallbackQuery):
    if callback.from_user.id not in ADMINS:
        await callback.answer("Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "Раздел Админ.\n\n"
        "Скоро здесь будет:\n"
        "- Управление юзерами\n"
        "- Глобальные настройки\n"
        "- Логи\n"
        "- EMERGENCY STOP\n\n"
        "В разработке.",
        reply_markup=main_menu_keyboard(callback.from_user.id, True),
    )
    await callback.answer()