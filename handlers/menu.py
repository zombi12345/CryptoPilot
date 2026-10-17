from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.main import main_menu_keyboard, main_reply_keyboard
from config import ADMINS

router = Router()


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_admin = user_id in ADMINS
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(user_id, is_admin),
    )


@router.message(F.text == "Меню")
async def reply_menu(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_admin = user_id in ADMINS
    await message.answer(
        "Главное меню:",
        reply_markup=main_menu_keyboard(user_id, is_admin),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("Действие отменено.")
    else:
        await message.answer("Нечего отменять.")


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    is_admin = user_id in ADMINS
    try:
        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=main_menu_keyboard(user_id, is_admin),
        )
    except Exception:
        await callback.message.answer(
            "Главное меню:",
            reply_markup=main_menu_keyboard(user_id, is_admin),
        )
    await callback.answer()