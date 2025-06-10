import asyncio
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, \
    KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func

from bot import bot
from config import RAZRAB, PASS_TIME
from db.models import Resident, Contractor, \
    AsyncSessionLocal, PermanentPass, TemporaryPass
from filters import IsSecurity

router = Router()
router.message.filter(IsSecurity())  # Применяем фильтр СБ ко всем хендлерам сообщений
router.callback_query.filter(IsSecurity())

security_reply_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Главное меню")]],
    resize_keyboard=True,
    is_persistent=True
)


class SearchStates(StatesGroup):
    WAITING_NUMBER = State()
    WAITING_DIGITS = State()


def get_security_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск пропуска", callback_data="search_pass")]
    ])


@router.message(CommandStart())
async def process_start_admin(message: Message):
    try:
        await message.answer(
            text="Здравствуйте администратор",
            reply_markup=security_reply_keyboard
        )
        await message.answer(
            text="Добро пожаловать в меню СБ",
            reply_markup=get_security_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text == "Главное меню")
async def main_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(
            text="Добро пожаловать в меню СБ",
            reply_markup=get_security_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        text="Добро пожаловать в меню СБ",
        reply_markup=get_security_menu()
    )


def get_search_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Поиск по номеру", callback_data="search_by_number")],
        [InlineKeyboardButton(text="🔢 Поиск по цифрам", callback_data="search_by_digits")],
        [InlineKeyboardButton(text="📋 Все временные пропуска", callback_data="all_temp_passes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


@router.callback_query(F.data == "search_pass")
async def search_pass_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            "Выберите тип поиска пропуска:",
            reply_markup=get_search_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "search_by_number")
async def start_search_by_number(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите номер машины полностью:")
        await state.set_state(SearchStates.WAITING_NUMBER)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, SearchStates.WAITING_NUMBER)
async def search_by_number(message: Message, state: FSMContext):
    try:
        car_number = message.text.upper().strip()
        today = datetime.now().date()
        found = False
        await state.clear()

        async with AsyncSessionLocal() as session:
            # 1. Поиск постоянных пропусков резидентов
            perm_stmt = select(PermanentPass, Resident.fio, Resident.plot_number) \
                .join(Resident, PermanentPass.resident_id == Resident.id) \
                .where(
                PermanentPass.car_number == car_number,
                PermanentPass.status == 'approved'
            )
            perm_result = await session.execute(perm_stmt)
            perm_passes = perm_result.all()

            admin_stmt = select(PermanentPass).where(
                PermanentPass.car_number == car_number,
                PermanentPass.status == 'approved',
                PermanentPass.resident_id == None
            )
            admin_result = await session.execute(admin_stmt)
            admin_passes = admin_result.scalars()

            temp_res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ).join(Resident, TemporaryPass.resident_id == Resident.id).where(
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today)

            temp_res_result = await session.execute(temp_res_stmt)
            temp_res_passes = temp_res_result.all()

            # 3. Поиск временных пропусков подрядчиков
            temp_contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                today <= func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days'))

            temp_contr_result = await session.execute(temp_contr_stmt)
            temp_contr_passes = temp_contr_result.all()

            temp_staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.car_number == car_number,
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                today <= func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days')
            )

            temp_staff_result = await session.execute(temp_staff_stmt)
            temp_staff_passes = temp_staff_result.scalars().all()

            # Обработка постоянных пропусков
            for pass_data in perm_passes:
                found = True
                perm_pass, fio, plot_number = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML")


            for pass_data in admin_passes:
                found = True
                perm_pass = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск представителя УК</b>\n\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"🏠 Место назначения: {perm_pass.destination}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML")



            # Обработка временных пропусков резидентов
            for pass_data in temp_res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                text = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in temp_contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                text = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {fio}\n"
                    f"🏢 Компания: {company}\n"
                    f"💼 Должность: {position}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            for temp_pass in temp_staff_passes:
                found = True
                text = (
                    "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            # Формируем итоговое сообщение
            if found:
                reply_text = "🔍 Поиск осуществлен"
            else:
                reply_text = "❌ Совпадений не найдено"

            await message.answer(
                reply_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "search_by_digits")
async def start_search_by_digits(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите часть номера машины:")
        await state.set_state(SearchStates.WAITING_DIGITS)
        await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, SearchStates.WAITING_DIGITS)
async def search_by_digits(message: Message, state: FSMContext):
    try:
        digits = message.text.strip()
        today = datetime.now().date()
        await state.clear()
        found = False

        async with AsyncSessionLocal() as session:
            # 1. Поиск постоянных пропусков
            perm_stmt = select(PermanentPass, Resident.fio, Resident.plot_number) \
                .join(Resident, PermanentPass.resident_id == Resident.id) \
                .where(
                PermanentPass.status == 'approved',
                PermanentPass.car_number.ilike(f"%{digits}%")
            )
            perm_result = await session.execute(perm_stmt)
            perm_passes = perm_result.all()

            admin_stmt = select(PermanentPass).where(
                PermanentPass.car_number.ilike(f"%{digits}%"),
                PermanentPass.status == 'approved',
                PermanentPass.resident_id == None
            )
            admin_result = await session.execute(admin_stmt)
            admin_passes = admin_result.scalars()


            # 2. Поиск временных пропусков резидентов
            temp_res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ) \
                .join(Resident, TemporaryPass.resident_id == Resident.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today,
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_res_result = await session.execute(temp_res_stmt)
            temp_res_passes = temp_res_result.all()

            # 3. Поиск временных пропусков подрядчиков
            temp_contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today,
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_contr_result = await session.execute(temp_contr_stmt)
            temp_contr_passes = temp_contr_result.all()

            temp_staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today,
                TemporaryPass.car_number.ilike(f"%{digits}%")
            )

            temp_staff_result = await session.execute(temp_staff_stmt)
            temp_staff_passes = temp_staff_result.scalars().all()

            # Обработка постоянных пропусков
            for pass_data in perm_passes:
                found = True
                perm_pass, fio, plot_number = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)


            for pass_data in admin_passes:
                found = True
                perm_pass = pass_data
                text = (
                    "🔰 <b>Постоянный пропуск представителя УК</b>\n\n"
                    f"🚗 Марка: {perm_pass.car_brand}\n"
                    f"🚙 Модель: {perm_pass.car_model}\n"
                    f"🔢 Номер: {perm_pass.car_number}\n"
                    f"🏠 Место назначения: {perm_pass.destination}\n"
                    f"👤 Владелец: {perm_pass.car_owner}\n"
                    f"📝 Комментарий для СБ: {perm_pass.security_comment or 'нет'}"
                )
                await asyncio.sleep(0.05)
                await message.answer(text, parse_mode="HTML")


            # Обработка временных пропусков резидентов
            for pass_data in temp_res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                text = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            # Обработка временных пропусков подрядчиков
            for pass_data in temp_contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                text = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {fio}\n"
                    f"🏢 Компания: {company}\n"
                    f"💼 Должность: {position}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            for temp_pass in temp_staff_passes:
                found = True
                text = (
                    "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)


        # Формируем итоговое сообщение
        if found:
            reply_text = "🔍 Поиск осуществлен"
        else:
            reply_text = "❌ Совпадений не найдено"

        await message.answer(
            reply_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
            )
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "all_temp_passes")
async def show_all_temp_passes(callback: CallbackQuery):
    try:
        today = datetime.now().date()
        found = False

        async with AsyncSessionLocal() as session:
            # Поиск временных пропусков резидентов
            res_stmt = select(
                TemporaryPass,
                Resident.fio,
                Resident.plot_number
            ) \
                .join(Resident, TemporaryPass.resident_id == Resident.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today)

            res_result = await session.execute(res_stmt)
            res_passes = res_result.all()

            # Поиск временных пропусков подрядчиков
            contr_stmt = select(
                TemporaryPass,
                Contractor.fio,
                Contractor.company,
                Contractor.position
            ) \
                .join(Contractor, TemporaryPass.contractor_id == Contractor.id) \
                .where(
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today)

            contr_result = await session.execute(contr_stmt)
            contr_passes = contr_result.all()

            staff_stmt = select(TemporaryPass).where(
                TemporaryPass.owner_type == 'staff',
                TemporaryPass.status == 'approved',
                TemporaryPass.visit_date <= today,
                func.date(TemporaryPass.visit_date, f'+{PASS_TIME} days') >= today
            )

            staff_result = await session.execute(staff_stmt)
            staff_passes = staff_result.scalars().all()

            # Обработка пропусков резидентов
            for pass_data in res_passes:
                found = True
                temp_pass, fio, plot_number = pass_data
                text = (
                    "⏳ <b>Временный пропуск резидента</b>\n\n"
                    f"👤 ФИО резидента: {fio}\n"
                    f"🏠 Номер участка: {plot_number}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await callback.message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            # Обработка пропусков подрядчиков
            for pass_data in contr_passes:
                found = True
                temp_pass, fio, company, position = pass_data
                text = (
                    "⏳ <b>Временный пропуск подрядчика</b>\n\n"
                    f"👷 ФИО подрядчика: {fio}\n"
                    f"🏢 Компания: {company}\n"
                    f"💼 Должность: {position}\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await callback.message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            for temp_pass in staff_passes:
                found = True
                text = (
                    "⏳ <b>Временный пропуск от представителя УК</b>\n\n"
                    f"🚗 Тип ТС: {'Легковой' if temp_pass.vehicle_type == 'car' else 'Грузовой'}\n"
                    f"🔢 Номер: {temp_pass.car_number}\n"
                    f"🚙 Марка: {temp_pass.car_brand}\n"
                    f"📦 Тип груза: {temp_pass.cargo_type}\n"
                    f"🏠 Место назначения: {temp_pass.destination}\n"
                    f"🎯 Цель визита: {temp_pass.purpose}\n"
                    f"📅 Дата визита: {temp_pass.visit_date.strftime('%d.%m.%Y')} - "
                    f"{(temp_pass.visit_date + timedelta(days=PASS_TIME)).strftime('%d.%m.%Y')}\n"
                    f"💬 Комментарий владельца: {temp_pass.owner_comment or 'нет'}\n"
                    f"📝 Комментарий для СБ: {temp_pass.security_comment or 'нет'}"
                )
                await callback.message.answer(text, parse_mode="HTML")
                await asyncio.sleep(0.05)

            # Формируем итоговое сообщение
            if found:
                reply_text = "🔍 Поиск осуществлен"
            else:
                reply_text = "❌ Актуальных временных пропусков не найдено"

            await callback.message.answer(
                reply_text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="search_pass")]]
                )
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)