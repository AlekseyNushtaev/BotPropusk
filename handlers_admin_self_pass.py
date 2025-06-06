# handlers_admin_self_pass.py
import asyncio

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import datetime

from sqlalchemy import select

from bot import bot
from config import ADMIN_IDS
from db.models import AsyncSessionLocal, TemporaryPass, Manager
from date_parser import parse_date
from db.util import get_active_admins_and_managers_tg_ids
from handlers_admin import admin_reply_keyboard
from handlers_admin_temporary_pass import get_passes_menu

router = Router()


class TemporarySelfPassStates(StatesGroup):
    CHOOSE_VEHICLE_TYPE = State()
    CHOOSE_WEIGHT_CATEGORY = State()
    CHOOSE_LENGTH_CATEGORY = State()
    INPUT_CAR_NUMBER = State()
    INPUT_CAR_BRAND = State()
    INPUT_CARGO_TYPE = State()
    INPUT_PURPOSE = State()
    INPUT_VISIT_DATE = State()
    INPUT_COMMENT = State()


async def get_owner_info(user_id: int) -> str:
    """Определяет информацию о владельце пропуска (админ/менеджер)"""
    if user_id in ADMIN_IDS:
        return "Администратор"

    async with AsyncSessionLocal() as session:
        manager = await session.scalar(
            select(Manager)
            .where(Manager.tg_id == user_id, Manager.status == True)
        )
        if manager and manager.fio:
            return f"Менеджер {manager.fio}"

    return "Сотрудник"


@router.callback_query(F.data == "issue_self_pass")
async def start_self_pass(callback: CallbackQuery, state: FSMContext):
    """Начало оформления временного пропуска для себя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Легковая", callback_data="self_vehicle_type_car")],
        [InlineKeyboardButton(text="Грузовая", callback_data="self_vehicle_type_truck")]
    ])
    await callback.message.edit_text("Выберите тип машины:", reply_markup=keyboard)
    await state.set_state(TemporarySelfPassStates.CHOOSE_VEHICLE_TYPE)


@router.callback_query(
    TemporarySelfPassStates.CHOOSE_VEHICLE_TYPE,
    F.data.startswith("self_vehicle_type_")
)
async def process_self_vehicle_type(callback: CallbackQuery, state: FSMContext):
    """Обработка типа транспортного средства"""
    vehicle_type = callback.data.split("_")[-1]
    await state.update_data(vehicle_type=vehicle_type)

    if vehicle_type == "truck":
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="≤ 12 тонн", callback_data="self_weight_light")],
            [InlineKeyboardButton(text="> 12 тонн", callback_data="self_weight_heavy")]
        ])
        await callback.message.answer("Выберите тоннаж:", reply_markup=keyboard)
        await state.set_state(TemporarySelfPassStates.CHOOSE_WEIGHT_CATEGORY)
    else:
        await callback.message.answer("Введите номер машины:")
        await state.set_state(TemporarySelfPassStates.INPUT_CAR_NUMBER)


@router.callback_query(
    TemporarySelfPassStates.CHOOSE_WEIGHT_CATEGORY,
    F.data.startswith("self_weight_")
)
async def process_self_weight_category(callback: CallbackQuery, state: FSMContext):
    """Обработка весовой категории для грузовиков"""
    weight_category = callback.data.split("_")[-1]
    await state.update_data(weight_category=weight_category)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="≤ 7 метров", callback_data="self_length_short")],
        [InlineKeyboardButton(text="> 7 метров", callback_data="self_length_long")]
    ])
    await callback.message.answer("Выберите длину машины:", reply_markup=keyboard)
    await state.set_state(TemporarySelfPassStates.CHOOSE_LENGTH_CATEGORY)


@router.callback_query(
    TemporarySelfPassStates.CHOOSE_LENGTH_CATEGORY,
    F.data.startswith("self_length_")
)
async def process_self_length_category(callback: CallbackQuery, state: FSMContext):
    """Обработка длины транспортного средства"""
    length_category = callback.data.split("_")[-1]
    await state.update_data(length_category=length_category)
    await callback.message.answer("Введите номер машины:")
    await state.set_state(TemporarySelfPassStates.INPUT_CAR_NUMBER)


@router.message(F.text, TemporarySelfPassStates.INPUT_CAR_NUMBER)
async def process_self_car_number(message: Message, state: FSMContext):
    """Обработка номера машины"""
    await state.update_data(car_number=message.text)
    await message.answer("Введите марку машины:")
    await state.set_state(TemporarySelfPassStates.INPUT_CAR_BRAND)


@router.message(F.text, TemporarySelfPassStates.INPUT_CAR_BRAND)
async def process_self_car_brand(message: Message, state: FSMContext):
    """Обработка марки машины"""
    await state.update_data(car_brand=message.text)
    await message.answer("Введите тип груза:")
    await state.set_state(TemporarySelfPassStates.INPUT_CARGO_TYPE)


@router.message(F.text, TemporarySelfPassStates.INPUT_CARGO_TYPE)
async def process_self_cargo_type(message: Message, state: FSMContext):
    """Обработка типа груза"""
    await state.update_data(cargo_type=message.text)
    await message.answer("Укажите назначение визита:")
    await state.set_state(TemporarySelfPassStates.INPUT_PURPOSE)


@router.message(F.text, TemporarySelfPassStates.INPUT_PURPOSE)
async def process_self_purpose(message: Message, state: FSMContext):
    """Обработка цели визита"""
    await state.update_data(purpose=message.text)
    await message.answer("Введите дату приезда (в формате ДД.ММ, ДД.ММ.ГГГГ или '5 июня'):")
    await state.set_state(TemporarySelfPassStates.INPUT_VISIT_DATE)


@router.message(F.text, TemporarySelfPassStates.INPUT_VISIT_DATE)
async def process_self_visit_date(message: Message, state: FSMContext):
    """Валидация и обработка даты визита"""
    user_input = message.text.strip()
    visit_date = parse_date(user_input)
    now = datetime.datetime.now().date()

    if not visit_date:
        await message.answer("❌ Неверный формат даты! Введите снова:")
        return

    if visit_date < now:
        await message.answer("❌ Дата не может быть меньше текущей! Введите снова:")
        return

    max_date = now + datetime.timedelta(days=31)
    if visit_date > max_date:
        await message.answer("❌ Пропуск нельзя заказать на месяц вперед! Введите снова:")
        return

    await state.update_data(visit_date=visit_date)
    await message.answer("Добавьте комментарий (если не требуется, напишите 'нет'):")
    await state.set_state(TemporarySelfPassStates.INPUT_COMMENT)


@router.message(F.text, TemporarySelfPassStates.INPUT_COMMENT)
async def process_self_comment_and_save(message: Message, state: FSMContext):
    """Сохранение временного пропуска с автоматическим подтверждением"""
    try:
        data = await state.get_data()
        comment = message.text if message.text.lower() != "нет" else None

        # Определяем информацию о владельце
        owner_info = await get_owner_info(message.from_user.id)

        async with AsyncSessionLocal() as session:
            new_pass = TemporaryPass(
                owner_type="staff",
                vehicle_type=data["vehicle_type"],
                weight_category=data.get("weight_category"),
                length_category=data.get("length_category"),
                car_number=data["car_number"].upper(),
                car_brand=data["car_brand"],
                cargo_type=data["cargo_type"],
                purpose=data["purpose"],
                visit_date=data["visit_date"],
                owner_comment=comment,
                security_comment=owner_info,
                status="approved",
                created_at=datetime.datetime.now(),
                time_registration=datetime.datetime.now()
            )
            session.add(new_pass)
            await session.commit()

        await message.answer(
            f"✅ Временный пропуск на машину {data['car_number'].upper()} оформлен!",
            reply_markup=get_passes_menu()
        )
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text=f'Пропуск от {owner_info} на машину с номером {data["car_number"].upper()} одобрен автоматически.\n(Пропуска > Временные пропуска > Подтвержденные)',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка при оформлении пропуска: {str(e)}")
        await state.clear()