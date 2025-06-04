import asyncio
import datetime
from typing import Union

from aiogram import Router, F
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, \
    CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from sqlalchemy import select, func, or_, and_

from bot import bot
from config import PAGE_SIZE, PASS_TIME, MAX_CAR_PASSES, MAX_TRUCK_PASSES, RAZRAB
from db.models import Resident, AsyncSessionLocal, ResidentContractorRequest, PermanentPass, TemporaryPass
from db.util import get_active_admins_and_managers_tg_ids
from filters import IsResident
from handlers_admin import admin_reply_keyboard

router = Router()
router.message.filter(IsResident())  # Применяем фильтр резидентства ко всем хендлерам сообщений
router.callback_query.filter(IsResident())  # Применяем фильтр резидентства ко всем хендлерам колбеков


class ResidentContractorRegistration(StatesGroup):
    INPUT_PHONE = State()
    INPUT_WORK_TYPES = State()


class PermanentPassStates(StatesGroup):
    INPUT_CAR_BRAND = State()
    INPUT_CAR_MODEL = State()
    INPUT_CAR_NUMBER = State()
    INPUT_CAR_OWNER = State()


class PermanentPassViewStates(StatesGroup):
    VIEWING_PENDING = State()
    VIEWING_APPROVED = State()
    VIEWING_REJECTED = State()


class TemporaryPassViewStates(StatesGroup):
    VIEWING_PENDING = State()
    VIEWING_APPROVED = State()
    VIEWING_REJECTED = State()


class TemporaryPassStates(StatesGroup):
    CHOOSE_VEHICLE_TYPE = State()
    CHOOSE_WEIGHT_CATEGORY = State()
    CHOOSE_LENGTH_CATEGORY = State()
    INPUT_CAR_NUMBER = State()
    INPUT_CAR_BRAND = State()
    INPUT_CARGO_TYPE = State()
    INPUT_PURPOSE = State()
    INPUT_VISIT_DATE = State()
    INPUT_COMMENT = State()


# Постоянная клавиатура для резидентов
resident_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Главное меню")]],
    resize_keyboard=True,
    is_persistent=True
)


main_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Зарегистрировать подрядчика", callback_data="register_contractor")],
    [InlineKeyboardButton(text="Постоянные пропуска", callback_data="permanent_pass_menu")],
    [InlineKeyboardButton(text="Временные пропуска", callback_data="temporary_pass_menu")],
    [InlineKeyboardButton(text="Обращения в УК", callback_data="appeals_menu")]  # Новая кнопка
])


@router.message(Command("start"))
async def resident_start(message: Message):
    """Обработчик команды /start для резидентов"""
    try:
        await message.answer(
            text="Добро пожаловать в личный кабинет резидента!",
            reply_markup=resident_keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text == "Главное меню")
async def main_menu(message: Message):
    try:
        """Обработчик главного меню резидента"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Resident)
                .where(Resident.tg_id == message.from_user.id)
            )
            resident = result.scalar()

            if not resident:
                return await message.answer("❌ Профиль не найден")

            caption = (
                f"👤 ФИО: {resident.fio}\n"
                f"🏠 Номер участка: {resident.plot_number}"
            )


            if resident.photo_id:
                await message.answer_photo(
                    photo=resident.photo_id,
                    caption=caption,
                    reply_markup=main_kb
                )
            else:
                await message.answer(
                    text="📷 Фото профиля отсутствует\n\n" + caption,
                    reply_markup=main_kb
                )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_main_menu")
async def main_menu(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Resident)
                .where(Resident.tg_id == callback.from_user.id)
            )
            resident = result.scalar()

            if not resident:
                return await callback.message.answer("❌ Профиль не найден")

            caption = (
                f"👤 ФИО: {resident.fio}\n"
                f"🏠 Номер участка: {resident.plot_number}"
            )


            if resident.photo_id:
                await callback.message.answer_photo(
                    photo=resident.photo_id,
                    caption=caption,
                    reply_markup=main_kb
                )
            else:
                await callback.message.answer(
                    text="📷 Фото профиля отсутствует\n\n" + caption,
                    reply_markup=main_kb
                )

    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)



@router.callback_query(F.data == "register_contractor")
async def start_contractor_registration(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите телефон подрядчика:")
        await state.set_state(ResidentContractorRegistration.INPUT_PHONE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, ResidentContractorRegistration.INPUT_PHONE)
async def process_contractor_phone(message: Message, state: FSMContext):
    try:
        await state.update_data(phone=message.text)
        await message.answer("Укажите виды выполняемых работ:")
        await state.set_state(ResidentContractorRegistration.INPUT_WORK_TYPES)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, ResidentContractorRegistration.INPUT_WORK_TYPES)
async def process_work_types(message: Message, state: FSMContext):
    try:
        data = await state.get_data()

        async with AsyncSessionLocal() as session:
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id))
            resident = resident.scalar()

            new_request = ResidentContractorRequest(
                resident_id=resident.id,
                phone=data['phone'],
                work_types=message.text
            )
            session.add(new_request)
            await session.commit()

            await message.answer("✅ Заявка на регистрацию подрядчика отправлена администратору!")
            tg_ids = await get_active_admins_and_managers_tg_ids()
            for tg_id in tg_ids:
                await bot.send_message(
                    tg_id,
                    text=f'Поступила заявка на регистрацию подрядчика от резидента {resident.fio}.\n(Регистрация > Заявки подрядчиков от резидентов)',
                    reply_markup=admin_reply_keyboard
                )
            caption = (
                f"👤 ФИО: {resident.fio}\n"
                f"🏠 Номер участка: {resident.plot_number}"
            )

            if resident.photo_id:
                await message.answer_photo(
                    photo=resident.photo_id,
                    caption=caption,
                    reply_markup=main_kb
                )
            else:
                await message.answer(
                    text="📷 Фото профиля отсутствует\n\n" + caption,
                    reply_markup=main_kb
                )
            await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Добавить новые обработчики
@router.callback_query(F.data == "permanent_pass_menu")
async def permanent_pass_menu(callback: CallbackQuery):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оформить постоянный пропуск", callback_data="create_permanent_pass")],
            [InlineKeyboardButton(text="На подтверждении", callback_data="my_pending_passes")],
            [InlineKeyboardButton(text="Подтвержденные", callback_data="my_approved_passes")],
            [InlineKeyboardButton(text="Отклоненные", callback_data="my_rejected_passes")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await callback.message.answer("Постоянные пропуска", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    try:
        await main_menu(callback.message)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "create_permanent_pass")
async def start_permanent_pass(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите марку машины:")
        await state.set_state(PermanentPassStates.INPUT_CAR_BRAND)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.INPUT_CAR_BRAND)
async def process_car_brand(message: Message, state: FSMContext):
    try:
        await state.update_data(car_brand=message.text)
        await message.answer("Введите модель машины:")
        await state.set_state(PermanentPassStates.INPUT_CAR_MODEL)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.INPUT_CAR_MODEL)
async def process_car_model(message: Message, state: FSMContext):
    try:
        await state.update_data(car_model=message.text)
        await message.answer("Введите номер машины:")
        await state.set_state(PermanentPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.INPUT_CAR_NUMBER)
async def process_car_number(message: Message, state: FSMContext):
    try:
        await state.update_data(car_number=message.text)
        await message.answer("Кому из членов Вашей семьи принадлежит автомобиль?")
        await state.set_state(PermanentPassStates.INPUT_CAR_OWNER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, PermanentPassStates.INPUT_CAR_OWNER)
async def process_car_owner(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        async with AsyncSessionLocal() as session:
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            new_request = PermanentPass(
                resident_id=resident.id,
                car_brand=data['car_brand'],
                car_model=data['car_model'],
                car_number=data['car_number'].upper(),
                car_owner=message.text
            )
            session.add(new_request)
            await session.commit()

        await message.answer("✅ Заявка на постоянный пропуск отправлена!")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text=f'Поступила заявка на постоянный пропуск от резидента {resident.fio}.\n(Пропуска > Постоянные пропуска > На утверждении)',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оформить постоянный пропуск", callback_data="create_permanent_pass")],
            [InlineKeyboardButton(text="На подтверждении", callback_data="my_pending_passes")],
            [InlineKeyboardButton(text="Подтвержденные", callback_data="my_approved_passes")],
            [InlineKeyboardButton(text="Отклоненные", callback_data="my_rejected_passes")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await message.answer("Постоянные пропуска", reply_markup=keyboard)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчики разделов пропусков
@router.callback_query(F.data == "my_pending_passes")
async def show_my_pending_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(PermanentPassViewStates.VIEWING_PENDING)
        await state.update_data(pass_page=0, pass_status='pending')
        await show_my_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_approved_passes")
async def show_my_approved_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(PermanentPassViewStates.VIEWING_APPROVED)
        await state.update_data(pass_page=0, pass_status='approved')
        await show_my_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_rejected_passes")
async def show_my_rejected_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(PermanentPassViewStates.VIEWING_REJECTED)
        await state.update_data(pass_page=0, pass_status='rejected')
        await show_my_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Функция отображения списка пропусков
async def show_my_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        page = data.get('pass_page', 0)
        status = data.get('pass_status', 'pending')

        async with AsyncSessionLocal() as session:
            # Получаем текущего резидента
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            if not resident:
                if isinstance(message, CallbackQuery):
                    await message.message.answer("❌ Резидент не найден")
                else:
                    await message.answer("❌ Резидент не найден")
                return

            # Получаем общее количество пропусков
            total_count = await session.scalar(
                select(func.count(PermanentPass.id))
                .where(
                    PermanentPass.resident_id == resident.id,
                    PermanentPass.status == status
                )
            )

            # Получаем пропуска для текущей страницы
            result = await session.execute(
                select(PermanentPass)
                .where(
                    PermanentPass.resident_id == resident.id,
                    PermanentPass.status == status
                )
                .order_by(PermanentPass.created_at.desc())
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            passes = result.scalars().all()

        if not passes:
            text = "У вас нет пропусков в этом разделе"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for pass_item in passes:
            btn_text = f"{pass_item.car_brand} {pass_item.car_model} - {pass_item.car_number}"
            if len(btn_text) > 30:
                btn_text = btn_text[:27] + "..."
            buttons.append(
                [InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"view_my_pass_{pass_item.id}"
                )]
            )

        # Кнопки пагинации
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data="my_pass_prev")
            )

        if (page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data="my_pass_next")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="permanent_pass_menu")]
        )

        status_text = {
            'pending': "на подтверждении",
            'approved': "подтвержденные",
            'rejected': "отклоненные"
        }.get(status, "")

        text = f"Ваши постоянные пропуска ({status_text}):"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


        # Обработчики пагинации
@ router.callback_query(F.data == "my_pass_prev", StateFilter(PermanentPassViewStates))
async def handle_my_pass_prev(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('pass_page', 0)
        if current_page > 0:
            await state.update_data(pass_page=current_page - 1)
            await show_my_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_pass_next", StateFilter(PermanentPassViewStates))
async def handle_my_pass_next(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('pass_page', 0)
        await state.update_data(pass_page=current_page + 1)
        await show_my_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


    # Просмотр деталей пропуска
@router.callback_query(F.data.startswith("view_my_pass_"))
async def view_my_pass_details(callback: CallbackQuery):
    try:
        pass_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            pass_item = await session.get(PermanentPass, pass_id)
            if not pass_item:
                await callback.answer("Пропуск не найден")
                return

            # Формируем текст
            status_text = {
                'pending': "⏳ На рассмотрении",
                'approved': "✅ Подтвержден",
                'rejected': "❌ Отклонен"
            }.get(pass_item.status, "")

            text = (
                f"Статус: {status_text}\n"
                f"Марка: {pass_item.car_brand}\n"
                f"Модель: {pass_item.car_model}\n"
                f"Номер: {pass_item.car_number}\n"
                f"Владелец: {pass_item.car_owner}\n"
                f"Дата подачи: {pass_item.created_at.strftime('%d.%m.%Y')}"
            )
            if pass_item.time_registration:
                if pass_item.status == 'approved':
                    text += f"\nДата подтверждения: {pass_item.time_registration.strftime('%d.%m.%Y')}"
                elif pass_item.status == 'rejected':
                    text += f"\nДата отклонения: {pass_item.time_registration.strftime('%d.%m.%Y')}"


            # Для отклоненных пропусков показываем комментарий
            if pass_item.status == 'rejected' and pass_item.resident_comment:
                text += f"\n\nКомментарий:\n{pass_item.resident_comment}"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_my_passes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Возврат к списку пропусков
@router.callback_query(F.data == "back_to_my_passes")
async def back_to_my_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_my_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "temporary_pass_menu")
async def temporary_pass_menu(callback: CallbackQuery):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
            [InlineKeyboardButton(text="На подтверждении", callback_data="my_pending_temp_passes")],
            [InlineKeyboardButton(text="Подтвержденные", callback_data="my_approved_temp_passes")],
            [InlineKeyboardButton(text="Отклоненные", callback_data="my_rejected_temp_passes")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        await callback.message.answer("Временные пропуска", reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "create_temporary_pass")
async def start_temporary_pass(callback: CallbackQuery, state: FSMContext):
    try:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Легковая", callback_data="vehicle_type_car")],
            [InlineKeyboardButton(text="Грузовая", callback_data="vehicle_type_truck")]
        ])
        await callback.message.answer("Выберите тип машины:", reply_markup=keyboard)
        await state.set_state(TemporaryPassStates.CHOOSE_VEHICLE_TYPE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_VEHICLE_TYPE, F.data.startswith("vehicle_type_"))
async def process_vehicle_type(callback: CallbackQuery, state: FSMContext):
    try:
        vehicle_type = callback.data.split("_")[-1]
        await state.update_data(vehicle_type=vehicle_type)

        if vehicle_type == "truck":
            # Для грузовиков запрашиваем тоннаж
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="≤ 12 тонн", callback_data="weight_light")],
                [InlineKeyboardButton(text="> 12 тонн", callback_data="weight_heavy")]
            ])
            await callback.message.answer("Выберите тоннаж:", reply_markup=keyboard)
            await state.set_state(TemporaryPassStates.CHOOSE_WEIGHT_CATEGORY)
        else:
            # Для легковых сразу переходим к номеру
            await callback.message.answer("Введите номер машины:")
            await state.set_state(TemporaryPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_WEIGHT_CATEGORY, F.data.startswith("weight_"))
async def process_weight_category(callback: CallbackQuery, state: FSMContext):
    try:
        weight_category = callback.data.split("_")[-1]
        await state.update_data(weight_category=weight_category)

        # Запрашиваем длину
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="≤ 7 метров", callback_data="length_short")],
            [InlineKeyboardButton(text="> 7 метров", callback_data="length_long")]
        ])
        await callback.message.answer("Выберите длину машины:", reply_markup=keyboard)
        await state.set_state(TemporaryPassStates.CHOOSE_LENGTH_CATEGORY)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(TemporaryPassStates.CHOOSE_LENGTH_CATEGORY, F.data.startswith("length_"))
async def process_length_category(callback: CallbackQuery, state: FSMContext):
    try:
        length_category = callback.data.split("_")[-1]
        await state.update_data(length_category=length_category)
        await callback.message.answer("Введите номер машины:")
        await state.set_state(TemporaryPassStates.INPUT_CAR_NUMBER)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка номера машины
@router.message(F.text, TemporaryPassStates.INPUT_CAR_NUMBER)
async def process_car_number(message: Message, state: FSMContext):
    try:
        await state.update_data(car_number=message.text)
        await message.answer("Введите марку машины:")
        await state.set_state(TemporaryPassStates.INPUT_CAR_BRAND)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка марки машины
@router.message(F.text, TemporaryPassStates.INPUT_CAR_BRAND)
async def process_car_brand(message: Message, state: FSMContext):
    try:
        await state.update_data(car_brand=message.text)
        await message.answer("Введите тип груза:")
        await state.set_state(TemporaryPassStates.INPUT_CARGO_TYPE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка типа груза
@router.message(F.text, TemporaryPassStates.INPUT_CARGO_TYPE)
async def process_cargo_type(message: Message, state: FSMContext):
    try:
        await state.update_data(cargo_type=message.text)
        await message.answer("Укажите назначение визита:")
        await state.set_state(TemporaryPassStates.INPUT_PURPOSE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка назначения визита
@router.message(F.text, TemporaryPassStates.INPUT_PURPOSE)
async def process_purpose(message: Message, state: FSMContext):
    try:
        await state.update_data(purpose=message.text)
        await message.answer("Введите дату приезда (в формате ДД.ММ.ГГГГ):")
        await state.set_state(TemporaryPassStates.INPUT_VISIT_DATE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработка даты приезда с валидацией
@router.message(F.text, TemporaryPassStates.INPUT_VISIT_DATE)
async def process_visit_date(message: Message, state: FSMContext):
    try:
        visit_date = datetime.datetime.strptime(message.text, "%d.%m.%Y").date()
        if visit_date < datetime.datetime.now().date():
            await message.answer("Дата не может быть меньше текущей даты. Введите снова:")
            return
        if visit_date > (datetime.datetime.now() + datetime.timedelta(days=31)).date():
            await message.answer("Пропуск нельзя заказать на месяц вперед. Введите снова:")
            return
        await state.update_data(visit_date=visit_date)
        await message.answer("Добавьте комментарий (если не требуется, напишите нет):")
        await state.set_state(TemporaryPassStates.INPUT_COMMENT)
    except ValueError:
        await message.answer("❌ Неверный формат даты! Введите в формате ДД.ММ.ГГГГ")


# Обработка комментария и сохранение данных
@router.message(F.text, TemporaryPassStates.INPUT_COMMENT)
async def process_comment_and_save(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        comment = message.text if message.text else None
        status = "pending"  # По умолчанию статус "на рассмотрении"

        async with AsyncSessionLocal() as session:
            # Получаем текущего резидента
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            if not resident:
                await message.answer("❌ Ошибка: резидент не найден")
                await state.clear()
                return

            # Даты для нового пропуска
            new_visit_date = data['visit_date']
            new_end_date = new_visit_date + datetime.timedelta(days=PASS_TIME)

            # Проверка лимитов для легковых автомобилей
            if data['vehicle_type'] == 'car':
                # Получаем все подходящие пропуска
                result = await session.execute(
                    select(TemporaryPass).where(
                        TemporaryPass.resident_id == resident.id,
                        TemporaryPass.vehicle_type == 'car',
                        TemporaryPass.status == 'approved',
                        TemporaryPass.visit_date <= new_end_date,  # Проверка начала существующего <= конца нового
                        func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= new_visit_date
                        # Проверка конца существующего >= начала нового
                    )
                )
                count = len(result.scalars().all())
                if count < MAX_CAR_PASSES:
                    status = "approved"

            # Проверка лимитов для малых грузовых автомобилей
            elif (data['vehicle_type'] == 'truck' and
                  data.get('weight_category') == 'light' and
                  data.get('length_category') == 'short'):

                # Проверяем количество подтвержденных малых грузовых пропусков, пересекающихся по датам
                result = await session.execute(
                    select(TemporaryPass).where(
                        TemporaryPass.resident_id == resident.id,
                        TemporaryPass.vehicle_type == 'truck',
                        TemporaryPass.status == 'approved',
                        TemporaryPass.visit_date <= new_end_date,  # Проверка начала существующего <= конца нового
                        func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= new_visit_date
                        # Проверка конца существующего >= начала нового
                    )
                )
                count = len(result.scalars().all())
                if count < MAX_TRUCK_PASSES:
                    status = "approved"

            # Создаем временный пропуск
            new_pass = TemporaryPass(
                owner_type="resident",
                resident_id=resident.id,
                vehicle_type=data.get("vehicle_type"),
                weight_category=data.get("weight_category", None),
                length_category=data.get("length_category", None),
                car_number=data.get("car_number").upper(),
                car_brand=data.get("car_brand"),
                cargo_type=data.get("cargo_type"),
                purpose=data.get("purpose"),
                visit_date=new_visit_date,
                owner_comment=comment,
                status=status,
                created_at=datetime.datetime.now(),
                time_registration=datetime.datetime.now() if status == "approved" else None
            )

            session.add(new_pass)
            await session.commit()
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")]
        ])
        if status == "approved":
            await message.answer("✅ Ваш временный пропуск одобрен автоматически!", reply_markup=keyboard)
        else:
            await message.answer("✅ Заявка на временный пропуск отправлена на рассмотрение!", reply_markup=keyboard)
            tg_ids = await get_active_admins_and_managers_tg_ids()
            for tg_id in tg_ids:
                await bot.send_message(
                    tg_id,
                    text=f'Поступила заявка на временный пропуск от резидента {resident.fio}.\n(Пропуска > Временные пропуска > На утверждении)',
                    reply_markup=admin_reply_keyboard
                )
                await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчики разделов временных пропусков
@router.callback_query(F.data == "my_pending_temp_passes")
async def show_my_pending_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_PENDING)
        await state.update_data(temp_pass_page=0, temp_pass_status='pending')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_approved_temp_passes")
async def show_my_approved_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_APPROVED)
        await state.update_data(temp_pass_page=0, temp_pass_status='approved')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_rejected_temp_passes")
async def show_my_rejected_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await state.set_state(TemporaryPassViewStates.VIEWING_REJECTED)
        await state.update_data(temp_pass_page=0, temp_pass_status='rejected')
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Функция отображения списка временных пропусков
async def show_my_temp_passes(message: Union[Message, CallbackQuery], state: FSMContext):
    try:
        data = await state.get_data()
        page = data.get('temp_pass_page', 0)
        status = data.get('temp_pass_status', 'pending')

        async with AsyncSessionLocal() as session:
            # Получаем текущего резидента
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            if not resident:
                if isinstance(message, CallbackQuery):
                    await message.answer("❌ Резидент не найден")
                else:
                    await message.answer("❌ Резидент не найден")
                return

            # Получаем общее количество пропусков
            total_count = await session.scalar(
                select(func.count(TemporaryPass.id))
                .where(
                    TemporaryPass.resident_id == resident.id,
                    TemporaryPass.status == status
                )
            )

            # Получаем пропуска для текущей страницы
            result = await session.execute(
                select(TemporaryPass)
                .where(
                    TemporaryPass.resident_id == resident.id,
                    TemporaryPass.status == status
                )
                .order_by(TemporaryPass.created_at.desc())
                .offset(page * PAGE_SIZE)
                .limit(PAGE_SIZE)
            )
            passes = result.scalars().all()

        if not passes:
            text = "У вас нет временных пропусков в этом разделе"
            if isinstance(message, CallbackQuery):
                await message.answer(text)
            else:
                await message.answer(text)
            return

        # Формируем кнопки
        buttons = []
        for pass_item in passes:
            # Формируем текст кнопки: дата + номер машины
            btn_text = f"{pass_item.visit_date.strftime('%d.%m.%Y')} - {pass_item.car_number}"
            if len(btn_text) > 30:
                btn_text = btn_text[:27] + "..."
            buttons.append(
                [InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"view_my_temp_pass_{pass_item.id}"
                )]
            )

        # Кнопки пагинации
        pagination_buttons = []
        if page > 0:
            pagination_buttons.append(
                InlineKeyboardButton(text="⬅️ Предыдущие", callback_data="my_temp_pass_prev")
            )

        if (page + 1) * PAGE_SIZE < total_count:
            pagination_buttons.append(
                InlineKeyboardButton(text="Следующие ➡️", callback_data="my_temp_pass_next")
            )

        if pagination_buttons:
            buttons.append(pagination_buttons)

        buttons.append(
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="temporary_pass_menu")]
        )

        status_text = {
            'pending': "на подтверждении",
            'approved': "подтвержденные",
            'rejected': "отклоненные"
        }.get(status, "")

        text = f"Ваши временные пропуска ({status_text}):"
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        else:
            await message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчики пагинации для временных пропусков
@router.callback_query(F.data == "my_temp_pass_prev", StateFilter(TemporaryPassViewStates))
async def handle_my_temp_pass_prev(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('temp_pass_page', 0)
        if current_page > 0:
            await state.update_data(temp_pass_page=current_page - 1)
            await show_my_temp_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "my_temp_pass_next", StateFilter(TemporaryPassViewStates))
async def handle_my_temp_pass_next(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        current_page = data.get('temp_pass_page', 0)
        await state.update_data(temp_pass_page=current_page + 1)
        await show_my_temp_passes(callback, state)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Просмотр деталей временного пропуска
@router.callback_query(F.data.startswith("view_my_temp_pass_"))
async def view_my_temp_pass_details(callback: CallbackQuery):
    try:
        pass_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            pass_item = await session.get(TemporaryPass, pass_id)
            if not pass_item:
                await callback.answer("Пропуск не найден")
                return

            # Формируем текст
            status_text = {
                'pending': "⏳ На рассмотрении",
                'approved': "✅ Подтвержден",
                'rejected': "❌ Отклонен"
            }.get(pass_item.status, "")

            # Определяем тип ТС
            vehicle_type = "Легковая" if pass_item.vehicle_type == "car" else "Грузовая"
            weight_category = ""
            length_category = ""

            if pass_item.vehicle_type == "truck":
                weight_category = "\nТоннаж: " + ("≤ 12 тонн" if pass_item.weight_category == "light" else "> 12 тонн")
                length_category = "\nДлина: " + ("≤ 7 метров" if pass_item.length_category == "short" else "> 7 метров")

            text = (
                f"Статус: {status_text}\n"
                f"Тип ТС: {vehicle_type}"
                f"{weight_category}"
                f"{length_category}\n"
                f"Номер: {pass_item.car_number}\n"
                f"Марка: {pass_item.car_brand}\n"
                f"Тип груза: {pass_item.cargo_type}\n"
                f"Цель визита: {pass_item.purpose}\n"
                f"Дата визита: {pass_item.visit_date.strftime('%d.%m.%Y')}\n"
                f"Комментарий: {pass_item.owner_comment or 'нет'}"
            )

            if pass_item.status == 'rejected' and pass_item.resident_comment:
                text += f"\n\nПричина отклонения:\n{pass_item.resident_comment}"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_my_temp_passes")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Возврат к списку временных пропусков
@router.callback_query(F.data == "back_to_my_temp_passes")
async def back_to_my_temp_passes(callback: CallbackQuery, state: FSMContext):
    try:
        await show_my_temp_passes(callback, state)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)
