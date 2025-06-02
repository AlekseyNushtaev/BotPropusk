import asyncio

from aiogram import Router, F
from aiogram.filters import CommandStart, ChatMemberUpdatedFilter, KICKED, MEMBER
from aiogram.types import Message, ContentType, CallbackQuery, ChatMemberUpdated
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from datetime import datetime

from bot import bot
from config import RAZRAB
from db.util import add_user_to_db, get_active_admins_and_managers_tg_ids

from db.models import (
    AsyncSessionLocal,
    Manager,
    Security,
    Resident,
    Contractor,
    RegistrationRequest,
    ContractorRegistrationRequest
)
from db.util import update_user_blocked, update_user_unblocked
from handlers_admin import is_valid_phone, admin_reply_keyboard
from handlers_security import security_reply_keyboard

router = Router()


class UserRegistration(StatesGroup):
    INPUT_FIO_CONTRACTOR = State()
    INPUT_COMPANY = State()
    INPUT_POSITION = State()
    INPUT_PHONE = State()
    INPUT_FIO = State()
    INPUT_PLOT = State()
    INPUT_PHOTO = State()


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED))
async def user_blocked_bot(event: ChatMemberUpdated):
    await update_user_blocked(event.from_user.id)


@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def user_unblocked_bot(event: ChatMemberUpdated):
    await update_user_unblocked(event.from_user.id)


async def check_existing_contractor_requests(tg_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ContractorRegistrationRequest)
            .filter(ContractorRegistrationRequest.tg_id == tg_id)
            .order_by(ContractorRegistrationRequest.created_at.desc())
        )
        return result.scalars().first()


async def check_existing_requests(tg_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest)
            .filter(RegistrationRequest.tg_id == tg_id)
            .order_by(RegistrationRequest.created_at.desc())
        )
        return result.scalars().first()


async def check_phone_in_tables(phone: str):
    async with AsyncSessionLocal() as session:
        # Check Manager
        result = await session.execute(select(Manager).filter(Manager.phone == phone))
        manager = result.scalars().first()
        if manager: return ('manager', manager)

        # Check Security
        result = await session.execute(select(Security).filter(Security.phone == phone))
        security = result.scalars().first()
        if security: return ('security', security)

        # Check Resident
        result = await session.execute(select(Resident).filter(Resident.phone == phone))
        resident = result.scalars().first()
        if resident: return ('resident', resident)

        # Check Contractor
        result = await session.execute(select(Contractor).filter(Contractor.phone == phone))
        contractor = result.scalars().first()
        if contractor:
            return ('contractor', contractor)

    return (None, None)


async def update_user_data(user_type, user_db, tg_user):
    async with AsyncSessionLocal() as session:
        user_db.tg_id = tg_user.id
        user_db.username = tg_user.username
        user_db.first_name = tg_user.first_name
        user_db.last_name = tg_user.last_name
        user_db.time_registration = datetime.now()
        user_db.status = True
        session.add(user_db)
        await session.commit()


@router.message(CommandStart())
async def process_start_user(message: Message, state: FSMContext):
    try:
        await add_user_to_db(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
            datetime.now()
        )
        resident_request = await check_existing_requests(message.from_user.id)
        contractor_request = await check_existing_contractor_requests(message.from_user.id)

        if resident_request or contractor_request:
            request = resident_request or contractor_request
            if request.status == 'pending':
                await message.answer("⏳ Ваша заявка находится в обработке")
                return
            elif request.status == 'rejected':
                text = f"❌ Ваша заявка отклонена. Причина: {request.admin_comment}\n\n"
                text += "Введите номер телефона для повторной регистрации:"
                await message.answer(text)
                await state.set_state(UserRegistration.INPUT_PHONE)
                return
            elif request.status == 'approved':
                await message.answer("✅ Ваша заявка одобрена! Добро пожаловать!")
                return

        await message.answer("Введите номер телефона:")
        await state.set_state(UserRegistration.INPUT_PHONE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, UserRegistration.INPUT_PHONE)
async def process_phone_input(message: Message, state: FSMContext):
    try:
        phone = message.text
        if not is_valid_phone(phone):
            await message.answer('Телефон должен быть в формате 8XXXXXXXXXX.\nПопробуйте ввести еще раз!')
            return
        user_type, user_db = await check_phone_in_tables(phone)

        if user_type in ['manager', 'security']:
            await update_user_data(user_type, user_db, message.from_user)
            await message.answer("Регистрация завершена! Добро пожаловать!", reply_markup=security_reply_keyboard)
            await state.clear()

        elif user_type == 'resident':
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(RegistrationRequest)
                    .filter(
                        RegistrationRequest.resident_id == user_db.id,
                        RegistrationRequest.status.in_(['pending', 'rejected'])
                    )
                )
                existing_request = result.scalars().first()

                if existing_request:
                    await state.clear()
                    if existing_request.status == 'pending':
                        await message.answer("Ваша заявка находится в обработке")
                        return

            await state.update_data(resident_id=user_db.id, phone=phone)
            await message.answer("Введите ФИО:")
            await state.set_state(UserRegistration.INPUT_FIO)

        elif user_type == 'contractor':
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(ContractorRegistrationRequest)
                    .filter(
                        ContractorRegistrationRequest.contractor_id == user_db.id,
                        ContractorRegistrationRequest.status.in_(['pending', 'rejected'])
                    )
                )
                existing_request = result.scalars().first()

                if existing_request:
                    await state.clear()
                    if existing_request.status == 'pending':
                        await message.answer("Ваша заявка находится в обработке")
                        return

            await state.update_data(contractor_id=user_db.id, phone=phone)
            await message.answer("Введите ФИО:")
            await state.set_state(UserRegistration.INPUT_FIO_CONTRACTOR)

        else:
            await message.answer("Номер не найден в системе. Введите телефон еще раз.")
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, UserRegistration.INPUT_FIO)
async def process_fio_input(message: Message, state: FSMContext):
    try:
        await state.update_data(fio=message.text)
        await message.answer("Введите номер участка:")
        await state.set_state(UserRegistration.INPUT_PLOT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, UserRegistration.INPUT_PLOT)
async def process_plot_input(message: Message, state: FSMContext):
    try:
        await state.update_data(plot_number=message.text)
        await message.answer("Отправьте свое фото:")
        await state.set_state(UserRegistration.INPUT_PHOTO)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(UserRegistration.INPUT_PHOTO, F.content_type == ContentType.PHOTO)
async def process_photo_input(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        photo_id = message.photo[-1].file_id

        async with AsyncSessionLocal() as session:
            new_request = RegistrationRequest(
                resident_id=data['resident_id'],
                fio=data['fio'],
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                plot_number=data['plot_number'],
                photo_id=photo_id
            )
            session.add(new_request)
            await session.commit()

        await message.answer("Заявка отправлена на модерацию")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text='Поступила заявка на регистрацию резидента (Регистрация > Регистрация резидентов',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, UserRegistration.INPUT_FIO_CONTRACTOR)
async def process_contractor_fio(message: Message, state: FSMContext):
    try:
        await state.update_data(fio=message.text)
        await message.answer("Введите название компании:")
        await state.set_state(UserRegistration.INPUT_COMPANY)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Добавить новый обработчик для компании:
@router.message(F.text, UserRegistration.INPUT_COMPANY)
async def process_company(message: Message, state: FSMContext):
    try:
        await state.update_data(company=message.text)
        await message.answer("Введите вашу должность:")
        await state.set_state(UserRegistration.INPUT_POSITION)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, UserRegistration.INPUT_POSITION)
async def process_position(message: Message, state: FSMContext):
    try:
        await state.update_data(position=message.text)
        data = await state.get_data()

        async with AsyncSessionLocal() as session:
            resident = await session.execute(
                select(Resident).where(Resident.tg_id == message.from_user.id)
            )
            resident = resident.scalar()

            new_request = ContractorRegistrationRequest(
                contractor_id=data['contractor_id'],
                fio=data['fio'],
                company=data['company'],  # Добавлено
                position=data['position'],  # Добавлено
                tg_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name
            )
            session.add(new_request)
            await session.commit()

        await message.answer("Заявка отправлена на модерацию!")
        tg_ids = await get_active_admins_and_managers_tg_ids()
        for tg_id in tg_ids:
            await bot.send_message(
                tg_id,
                text='Поступила заявка на регистрацию подрядчика (Регистрация > Регистрация подрядчика',
                reply_markup=admin_reply_keyboard
            )
            await asyncio.sleep(0.05)
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "restart")
async def restart_application(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите номер телефона:")
        await state.set_state(UserRegistration.INPUT_PHONE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)
