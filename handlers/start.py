from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from states import StartStates
from keyboards.main import main_menu_keyboard, main_reply_keyboard
from database import create_user_if_missing, set_agreed
from config import ADMINS

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await create_user_if_missing(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )

    text = (
        "Добро пожаловать в Trading Bot.\n\n"
        "Этот бот - инструмент для анализа графиков и автоматизации торговли.\n"
        "Он НЕ является инвестиционным советником.\n\n"
        "РИСКИ:\n"
        "- Торговля криптовалютами связана с риском потери капитала\n"
        "- Прогнозы AI могут быть ошибочными\n"
        "- Вы можете потерять весь депозит\n\n"
        "ОТВЕТСТВЕННОСТЬ:\n"
        "- Вы торгуете на свой страх и риск\n"
        "- Разработчик не несёт ответственности за убытки\n"
        "- Все решения принимаете вы\n\n"
        "Нажимая Согласен, вы подтверждаете, что понимаете риски "
        "и используете бота на свой страх и риск."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Я понимаю и согласен", callback_data="agree_yes")],
        [InlineKeyboardButton(text="Отмена", callback_data="agree_no")],
    ])
    await message.answer(text, reply_markup=kb)
    await state.set_state(StartStates.waiting_agree)


@router.callback_query(StartStates.waiting_agree, F.data == "agree_yes")
async def agree_yes(callback, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await create_user_if_missing(
        user_id,
        callback.from_user.username or "",
        callback.from_user.first_name or "",
    )
    await set_agreed(user_id)
    is_admin = user_id in ADMINS
    await callback.message.edit_text("Согласовано.\n\nГлавное меню:")
    await callback.message.answer(
        "Выбери раздел:",
        reply_markup=main_reply_keyboard(),
    )
    await callback.message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(user_id, is_admin),
    )
    await callback.answer()


@router.callback_query(StartStates.waiting_agree, F.data == "agree_no")
async def agree_no(callback, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено. Напиши /start чтобы начать заново.")
    await callback.answer()


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    await create_user_if_missing(
        user_id,
        message.from_user.username or "",
        message.from_user.first_name or "",
    )
    is_admin = user_id in ADMINS
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(user_id, is_admin),
    )