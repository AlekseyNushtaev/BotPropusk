import asyncio
import datetime

from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, \
    KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from sqlalchemy import select, delete

from bot import bot
from config import ADMIN_IDS, RAZRAB
from db.models import Manager, Security, Resident, Contractor, RegistrationRequest, \
    ContractorRegistrationRequest, AsyncSessionLocal, ResidentContractorRequest, PermanentPass, TemporaryPass, Appeal

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))  # Применяем фильтр резидентства ко всем хендлерам сообщений
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))  # Применяем фильтр резидентства ко всем хендлерам колбеков


class AddUserStates(StatesGroup):
    WAITING_PHONE = State()
    CHOOSE_TYPE = State()


class RegistrationRequestStates(StatesGroup):
    AWAIT_REJECT_RESIDENT_COMMENT = State()
    AWAIT_EDIT_COMPANY = State()  # Добавлено
    AWAIT_EDIT_POSITION = State()  # Добавлено
    AWAIT_EDIT_CONTRACTOR_FIO = State()
    EDITING_CONTRACTOR_REQUEST = State()
    VIEWING_CONTRACTOR_REQUEST = State()
    AWAIT_REJECT_CONTRACTOR_COMMENT = State()
    VIEWING_REQUEST = State()
    EDITING_REQUEST = State()
    AWAIT_EDIT_FIO = State()
    AWAIT_EDIT_PLOT = State()
    AWAIT_EDIT_PHOTO = State()
    AWAIT_REJECT_COMMENT = State()


@router.callback_query(F.data == "back_to_main")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        text="Добро пожаловать в меню администратора",
        reply_markup=get_admin_menu()
    )


admin_reply_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Главное меню")]],
    resize_keyboard=True,
    is_persistent=True
)


def is_valid_phone(phone: str) -> bool:
    return len(phone) == 11 and phone.isdigit() and phone[0] == '8'


def edit_keyboard_contractor():
    return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="ФИО", callback_data="edit_contractorfio"),
                InlineKeyboardButton(text="Компания", callback_data="edit_contractorcompany"),  # Добавлено
            ],
            [
                InlineKeyboardButton(text="Должность", callback_data="edit_contractorposition"),  # Добавлено
            ],
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="edit_finishcontractor")
            ]
        ])


def get_registration_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Регистрация резидентов", callback_data="registration_requests")],
        [InlineKeyboardButton(text="Регистрация подрядчиков", callback_data="contractor_requests")],
        [InlineKeyboardButton(text="Заявки подрядчиков от резидентов", callback_data="resident_contractor_requests")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ])


# Обновленное главное меню админа
def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥Управление пользователями", callback_data="user_management")],
        [InlineKeyboardButton(text="📝 Регистрация", callback_data="registration_menu")],
        [InlineKeyboardButton(text="🚪 Пропуска", callback_data="passes_menu")],
        [InlineKeyboardButton(text="🔍 Поиск пропуска", callback_data="search_pass")],
        [InlineKeyboardButton(text="📈Статистика", callback_data="statistics_menu")],
        [InlineKeyboardButton(text="📨 Обращения в УК", callback_data="appeals_management")]  # Новая кнопка
    ])


def edit_keyboard_resident():
    return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="ФИО", callback_data="edit_fio"),
                InlineKeyboardButton(text="Номер участка", callback_data="edit_plot")
            ],
            [
                InlineKeyboardButton(text="✅ Готово", callback_data="edit_finish")
            ]
        ])


def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back")]
    ])


def get_admin_menu_with_back():
    buttons = get_admin_menu().inline_keyboard
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_management_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Менеджеры", callback_data="managers_manage")],
        [InlineKeyboardButton(text="СБ", callback_data="security_manage")],
        [InlineKeyboardButton(text="Резиденты", callback_data="residents_manage")],
        [InlineKeyboardButton(text="Подрядчики", callback_data="contractors_manage")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
        ])


def get_add_menu(user_type: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Добавить {user_type}", callback_data=f"add_{user_type}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
        ])


@router.message(CommandStart())
async def process_start_admin(message: Message):
    try:
        await message.answer(
            text="Здравствуйте администратор",
            reply_markup=admin_reply_keyboard
        )
        await message.answer(
            text="Добро пожаловать в меню администратора",
            reply_markup=get_admin_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text == "Главное меню")
async def main_menu(message: Message, state: FSMContext):
    try:
        await state.clear()
        await message.answer(
            text="Добро пожаловать в меню администратора",
            reply_markup=get_admin_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.in_({"user_management", "back_to_manage"}))
async def user_management(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            text="Выберите категорию пользователей:",
            reply_markup=get_user_management_menu()
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.endswith("manage"))
async def manage_category(callback: CallbackQuery, state: FSMContext):
    try:
        user_type = callback.data.split("_")[0]
        await state.update_data(user_type=user_type)

        # Для резидентов
        if user_type == 'residents':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить резидента", callback_data=f"add_{user_type}")],
                [InlineKeyboardButton(text="Список резидентов", callback_data="list_residents")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
            ])
        # Для подрядчиков
        elif user_type == 'contractors':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить подрядчика", callback_data=f"add_{user_type}")],
                [InlineKeyboardButton(text="Список подрядчиков", callback_data="list_contractors")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
            ])
        elif user_type == 'managers':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить менеджера", callback_data=f"add_{user_type}")],
                [InlineKeyboardButton(text="Список менеджеров", callback_data="list_managers")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
            ])
            # Для СБ
        elif user_type == 'security':
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Добавить СБ", callback_data=f"add_{user_type}")],
                [InlineKeyboardButton(text="Список СБ", callback_data="list_security")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
            ])
        else:
            return

        await callback.message.edit_text(
            text=f"Управление {user_type}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("add_"))
async def start_add_user(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите телефон пользователя:")
        await state.set_state(AddUserStates.WAITING_PHONE)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, AddUserStates.WAITING_PHONE)
async def process_phone(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        user_type = data['user_type']
        phone = message.text
        if not is_valid_phone(phone):
            await message.answer('Телефон должен быть в формате 8XXXXXXXXXX.\nПопробуйте ввести еще раз!')
            return

        async with AsyncSessionLocal() as session:
            try:
                if user_type == 'managers':
                    new_user = Manager(phone=phone)
                elif user_type == 'security':
                    new_user = Security(phone=phone)
                elif user_type == 'residents':
                    new_user = Resident(phone=phone)
                elif user_type == 'contractors':
                    new_user = Contractor(phone=phone)

                session.add(new_user)
                await session.commit()
                await message.answer(f"Пользователь с телефоном {phone} добавлен в {user_type}!")
                if user_type == 'residents':
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Добавить резидента", callback_data=f"add_{user_type}")],
                        [InlineKeyboardButton(text="Список резидентов", callback_data="list_residents")],
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
                    ])
                # Для подрядчиков
                elif user_type == 'contractors':
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Добавить подрядчика", callback_data=f"add_{user_type}")],
                        [InlineKeyboardButton(text="Список подрядчиков", callback_data="list_contractors")],
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
                    ])
                # Для остальных
                elif user_type == 'managers':
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Добавить менеджера", callback_data=f"add_{user_type}")],
                        [InlineKeyboardButton(text="Список менеджеров", callback_data="list_managers")],
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
                    ])
                    # Для СБ
                elif user_type == 'security':
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="Добавить СБ", callback_data=f"add_{user_type}")],
                        [InlineKeyboardButton(text="Список СБ", callback_data="list_security")],
                        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
                    ])
                else:
                    return

                await message.answer(
                    text=f"Управление {user_type}:",
                    reply_markup=keyboard
                )

            except Exception as e:
                await message.answer(f"Ошибка: {str(e)}")
                await session.rollback()

        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "registration_menu")
async def show_registration_menu(callback: CallbackQuery):
    try:
        await callback.message.edit_text(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик кнопки "Заявки на регистрацию"
@router.callback_query(F.data == "registration_requests")
async def show_pending_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(RegistrationRequest)
                .filter(RegistrationRequest.status == 'pending')
            )
            requests = result.scalars().all()

            if not requests:
                await callback.answer("Нет заявок в ожидании")
                return

            buttons = [
                [InlineKeyboardButton(
                    text=f"Резидент - {req.resident_id}",
                    callback_data=f"view_request_{req.id}"
                )]
                for req in requests
            ]

            await callback.message.edit_text(
                "Заявки на регистрацию:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик для заявок подрядчиков
@router.callback_query(F.data == "contractor_requests")
async def show_contractor_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ContractorRegistrationRequest)
                .filter(ContractorRegistrationRequest.status == 'pending')
            )
            requests = result.scalars().all()

            if not requests:
                await callback.answer("Нет заявок подрядчиков")
                return

            buttons = [
                [InlineKeyboardButton(
                    text=f"Подрядчик - {req.fio}",
                    callback_data=f"view_contractor_request_{req.id}"
                )] for req in requests
            ]

            await callback.message.edit_text(
                "Заявки подрядчиков:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обработчик выбора заявки
@router.callback_query(F.data.startswith("view_request_"))
async def view_request_details(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)

            await state.update_data(current_request_id=request_id)

            # Формируем сообщение с фото и данными
            caption = (
                f"ФИО: {request.fio}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            # Кнопки действий
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_requests")]
            ])

            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=request.photo_id,
                caption=caption,
                reply_markup=keyboard
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Просмотр заявки подрядчика
@router.callback_query(F.data.startswith("view_contractor_request_"))
async def view_contractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])
        await state.update_data(current_contractor_request_id=request_id)

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_contractor_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_contractor_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_contractor_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="contractor_requests")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки
@router.callback_query(F.data == "approve_request")
async def approve_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            # Обновляем данные резидента
            resident.fio = request.fio
            resident.plot_number = request.plot_number
            resident.photo_id = request.photo_id
            resident.tg_id = request.tg_id
            resident.username = request.username
            resident.time_registration = datetime.datetime.now()
            resident.status = True

            request.status = 'approved'
            await session.commit()

            # Отправляем уведомление пользователю
            await bot.send_message(
                chat_id=request.tg_id,
                text="🎉 Поздравляем с успешной регистрацией в качестве резидента! Для управления нажмите кнопку Главное меню.",
                reply_markup=admin_reply_keyboard
            )

            await callback.message.edit_caption(caption="✅ Заявка одобрена")
            await callback.message.answer(
                text="Меню регистрации:",
                reply_markup=get_registration_menu()
            )
            await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки подрядчика
@router.callback_query(F.data == "approve_contractor_request")
async def approve_contractor_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            contractor = await session.get(Contractor, request.contractor_id)

            contractor.fio = request.fio
            contractor.company = request.company
            contractor.position = request.position
            contractor.affiliation = request.affiliation
            contractor.tg_id = request.tg_id
            contractor.username = request.username
            contractor.status = True
            contractor.time_registration = datetime.datetime.now()

            request.status = 'approved'
            await session.commit()

            await bot.send_message(
                request.tg_id,
                "🎉 Поздравляем с успешной регистрацией в качестве подрядчика! Для управления нажмите кнопку Главное меню.",
                reply_markup=admin_reply_keyboard
            )

        await callback.message.edit_text("✅ Заявка одобрена")
        await callback.message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало редактирования
@router.callback_query(F.data == "edit_request")
async def start_editing(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=edit_keyboard_resident())
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Начало редактирования
@router.callback_query(F.data == "edit_contractor_request")
async def start_contractor_editing(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_reply_markup(reply_markup=edit_keyboard_contractor())
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_finish", RegistrationRequestStates.EDITING_REQUEST)
async def finish_editing(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)

            # Формируем обновленное сообщение
            caption = (
                f"ФИО: {request.fio}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            # Создаем клавиатуру с основными кнопками
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="requests")]
            ])

            # Удаляем старое сообщение с редактором
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )

            # Отправляем новое сообщение с актуальными данными
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=request.photo_id,
                caption=caption,
                reply_markup=keyboard
            )

        await state.set_state(RegistrationRequestStates.VIEWING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "edit_finishcontractor", RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
async def finish_editing(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)

            # Формируем обновленное сообщение
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            # Создаем клавиатуру с основными кнопками
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_contractor_request")],
                [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_contractor_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_contractor_request")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="contractor_requests")]
            ])

            # Удаляем старое сообщение с редактором
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )

            # Отправляем новое сообщение с актуальными данными
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=text,
                reply_markup=keyboard
            )

        await state.set_state(RegistrationRequestStates.VIEWING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("edit_"), RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
async def handle_edit_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.split("_")[-1]

        if action == "contractorfio":
            await callback.message.answer("Введите новое ФИО:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_CONTRACTOR_FIO)
        elif action == "contractorcompany":  # Добавлено
            await callback.message.answer("Введите новое название компании:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_COMPANY)
        elif action == "contractorposition":  # Добавлено
            await callback.message.answer("Введите новую должность:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_POSITION)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("edit_"), RegistrationRequestStates.EDITING_REQUEST)
async def handle_edit_actions(callback: CallbackQuery, state: FSMContext):
    try:
        action = callback.data.split("_")[-1]

        if action == "fio":
            await callback.message.answer("Введите новое ФИО:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_FIO)
        elif action == "plot":
            await callback.message.answer("Введите новый номер участка:")
            await state.set_state(RegistrationRequestStates.AWAIT_EDIT_PLOT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление ФИО
@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_FIO)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.fio = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            caption = (
                f"ФИО: {message.text}\n"
                f"Участок: {request.plot_number}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )
            await bot.send_photo(
                chat_id=message.from_user.id,
                photo=request.photo_id,
                caption=caption,
                reply_markup=edit_keyboard_resident()
            )
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_CONTRACTOR_FIO)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.fio = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            text = (
                f"ФИО: {message.text}\n"
                f"Компания: {request.company}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_COMPANY)
async def update_company(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.company = message.text
            await session.commit()
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {message.text}\n"
                f"Должность: {request.position}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_POSITION)
async def update_position(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']
        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.position = message.text
            await session.commit()
            text = (
                f"ФИО: {request.fio}\n"
                f"Компания: {request.company}\n"
                f"Должность: {message.text}\n"
                f"TG: @{request.username}\n"
                f"Принадлежность: {request.affiliation}\n"
            )

            await bot.send_message(
                chat_id=message.from_user.id,
                text=text,
                reply_markup=edit_keyboard_contractor()
            )
        await state.set_state(RegistrationRequestStates.EDITING_CONTRACTOR_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Обновление Номер участка
@router.message(F.text, RegistrationRequestStates.AWAIT_EDIT_PLOT)
async def update_fio(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.plot_number = message.text
            await session.commit()
            # Формируем сообщение с фото и данными
            caption = (
                f"ФИО: {request.fio}\n"
                f"Участок: {message.text}\n"
                f"TG ID: {request.tg_id}\n"
                f"Username: @{request.username}"
            )

            await bot.send_photo(
                chat_id=message.from_user.id,
                photo=request.photo_id,
                caption=caption,
                reply_markup=edit_keyboard_resident()
            )
        await state.set_state(RegistrationRequestStates.EDITING_REQUEST)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Отклонение заявки
@router.callback_query(F.data == "reject_request")
async def start_reject(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_CONTRACTOR_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_CONTRACTOR_COMMENT)
async def reject_request(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_contractor_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ContractorRegistrationRequest, request_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

            # Уведомление пользователя
            await bot.send_message(
                chat_id=request.tg_id,
                text=f"❌ Ваша заявка отклонена.\nПричина: {message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="Заполнить заново", callback_data="restart")]]))

        await message.answer("Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Отклонение заявки
@router.callback_query(F.data == "reject_contractor_request")
async def start_reject(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите комментарий для отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_COMMENT)
async def reject_request(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(RegistrationRequest, request_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

            # Уведомление пользователя
            await bot.send_message(
                chat_id=request.tg_id,
                text=f"❌ Ваша заявка отклонена.\nПричина: {message.text}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="Заполнить заново", callback_data="restart")]]))

        await message.answer("Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "resident_contractor_requests")
async def show_resident_contractor_requests(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ResidentContractorRequest)
                .filter(ResidentContractorRequest.status == 'pending')
            )
            requests = result.scalars().all()

            buttons = [
                [InlineKeyboardButton(
                    text=f"Подрядчик от резидента #{req.id}",
                    callback_data=f"view_resident_request_{req.id}"
                )] for req in requests
            ]

            await callback.message.edit_text(
                "Заявки на подрядчиков от резидентов:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    *buttons,
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="registration_menu")]]
                )
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_resident_request_"))
async def view_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        request_id = int(callback.data.split("_")[-1])
        await state.update_data(current_resident_request_id=request_id)

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            text = (
                f"📱 Телефон: {request.phone}\n"
                f"🏗 Виды работ: {request.work_types}\n"
                f"👤 Резидент: {resident.fio} (ID: {resident.id})"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Одобрить", callback_data="approve_resident_request")],
                [InlineKeyboardButton(text="❌ Отклонить", callback_data="reject_resident_request")]
            ])

            await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Одобрение заявки
@router.callback_query(F.data == "approve_resident_request")
async def approve_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_resident_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)

            # Создаем запись подрядчика
            new_contractor = Contractor(
                phone=request.phone,
                work_types=request.work_types,
                affiliation=f"{resident.id}_{resident.fio}",
                status=False  # Требует завершения регистрации
            )
            session.add(new_contractor)
            await session.commit()

            # Обновляем статус заявки
            request.status = 'approved'
            await session.commit()

        await bot.send_message(
            chat_id=resident.tg_id,
            text=f"🎉 Заявка на регистрацию Вашего подрядчика ({request.phone}) одобрена! Для завершения регистрации подрядчика, перешлите "
                 "подрядчику ссылку на бот, подрядчик должен ввести номер телефона, который вы указали для его регистрации.",
            reply_markup=admin_reply_keyboard
        )
        await callback.message.edit_text("✅ Заявка одобрена!")
        await callback.message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "reject_resident_request")
async def reject_resident_request(callback: CallbackQuery, state: FSMContext):
    try:
        await callback.message.answer("Введите причину отклонения:")
        await state.set_state(RegistrationRequestStates.AWAIT_REJECT_RESIDENT_COMMENT)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.message(F.text, RegistrationRequestStates.AWAIT_REJECT_RESIDENT_COMMENT)
async def process_reject_comment(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        request_id = data['current_resident_request_id']

        async with AsyncSessionLocal() as session:
            request = await session.get(ResidentContractorRequest, request_id)
            resident = await session.get(Resident, request.resident_id)
            request.status = 'rejected'
            request.admin_comment = message.text
            await session.commit()

        await bot.send_message(
            chat_id=resident.tg_id,
            text=f"❌ Заявка на регистрацию Вашего подрядчика ({request.phone}) отклонена!\nПричина: {message.text}",
            reply_markup=admin_reply_keyboard
        )
        await message.edit_text("❌ Заявка отклонена!")
        await message.answer(
            text="Меню регистрации:",
            reply_markup=get_registration_menu()
        )
        await state.clear()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{message.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "list_residents")
async def show_residents_list(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            # Получаем всех резидентов со статусом True
            result = await session.execute(
                select(Resident).where(Resident.status == True))
            residents = result.scalars().all()

            if not residents:
                await callback.answer("Нет зарегистрированных резидентов")
                return

            buttons = []
            for resident in residents:
                # Формируем текст кнопки: ID и ФИО
                button_text = f"{resident.id}_{resident.fio}"
                # Укорачиваем, если слишком длинное
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."

                buttons.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_resident_{resident.id}"
                )])

            # Добавляем кнопку "Назад"
            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="residents_manage"
            )])
            try:
                await callback.message.edit_text(
                    "Список зарегистрированных резидентов:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )
            except:
                await callback.message.answer(text="Список зарегистрированных резидентов:",
                                              reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_resident_"))
async def view_resident_details(callback: CallbackQuery):
    try:
        resident_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            resident = await session.get(Resident, resident_id)
            if not resident:
                await callback.answer("Резидент не найден")
                return

            # Формируем текст
            text = (
                f"ID: {resident.id}\n"
                f"ФИО: {resident.fio}\n"
                f"Телефон: {resident.phone}\n"
                f"Номер участка: {resident.plot_number}\n"
                f"TG: @{resident.username}\n"
                f"Время регистрации: {resident.time_registration}"
            )

            # Клавиатура с кнопкой "Назад" к списку резидентов
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_resident_{resident_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="list_residents")]
            ])

            # Отправляем фото, если есть
            if resident.photo_id:
                await bot.send_photo(
                    chat_id=callback.from_user.id,
                    photo=resident.photo_id,
                    caption=text,
                    reply_markup=keyboard
                )
            else:
                await callback.message.answer(
                    text=text,
                    reply_markup=keyboard
                )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# ... существующий код ...

@router.callback_query(F.data == "list_contractors")
async def show_contractors_list(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            # Получаем всех подрядчиков со статусом True
            result = await session.execute(
                select(Contractor).where(Contractor.status == True))
            contractors = result.scalars().all()

            if not contractors:
                await callback.answer("Нет зарегистрированных подрядчиков")
                return

            buttons = []
            for contractor in contractors:
                # Формируем текст кнопки: ID и ФИО
                button_text = f"{contractor.id}_{contractor.fio}"
                # Укорачиваем, если слишком длинное
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."

                buttons.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_contractor_{contractor.id}"
                )])

            # Добавляем кнопку "Назад"
            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="contractors_manage"
            )])

            try:
                await callback.message.edit_text(
                    "Список зарегистрированных подрядчиков:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )
            except:
                await callback.message.answer(
                    text="Список зарегистрированных подрядчиков:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
                )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_contractor_"))
async def view_contractor_details(callback: CallbackQuery):
    try:
        contractor_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            contractor = await session.get(Contractor, contractor_id)
            if not contractor:
                await callback.answer("Подрядчик не найден")
                return

            # Формируем текст
            text = (
                f"ID: {contractor.id}\n"
                f"ФИО: {contractor.fio}\n"
                f"Телефон: {contractor.phone}\n"
                f"Компания: {contractor.company}\n"
                f"Должность: {contractor.position}\n"
                f"Принадлежность: {contractor.affiliation}\n"
                f"TG: @{contractor.username}\n"
                f"Время регистрации: {contractor.time_registration}"
            )

            # Клавиатура с кнопкой "Назад" к списку подрядчиков
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_contractor_{contractor_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="list_contractors")]
            ])

            await callback.message.answer(
                text=text,
                reply_markup=keyboard
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("delete_resident_"))
async def confirm_delete_resident(callback: CallbackQuery):
    try:
        resident_id = int(callback.data.split("_")[-1])
        await callback.message.answer(
            "Вы точно хотите удалить резидента?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_yes_{resident_id}")],
                [InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_delete_no_{resident_id}")]
            ])
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("confirm_delete_no_"))
async def cancel_delete(callback: CallbackQuery):
    try:
        resident_id = int(callback.data.split("_")[-1])
        # Возвращаемся к просмотру резидента
        await view_resident_details(callback)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("confirm_delete_yes_"))
async def execute_delete(callback: CallbackQuery, state: FSMContext):
    try:
        resident_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            # Удаляем связанные заявки
            stmt1 = delete(RegistrationRequest).where(RegistrationRequest.resident_id == resident_id)
            stmt2 = delete(ResidentContractorRequest).where(ResidentContractorRequest.resident_id == resident_id)
            stmt3 = delete(PermanentPass).where(PermanentPass.resident_id == resident_id)
            stmt4 = delete(TemporaryPass).where(TemporaryPass.resident_id == resident_id)
            stmt5 = delete(Appeal).where(Appeal.resident_id == resident_id)
            await session.execute(stmt1)
            await session.execute(stmt2)
            await session.execute(stmt3)
            await session.execute(stmt4)
            await session.execute(stmt5)

            # Удаляем резидента
            stmt6 = delete(Resident).where(Resident.id == resident_id)
            await session.execute(stmt6)
            await session.commit()

        await callback.message.answer("✅ Резидент удален")
        # Возвращаемся в меню управления резидентами
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить резидента", callback_data=f"add_residents")],
            [InlineKeyboardButton(text="Список резидентов", callback_data="list_residents")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
        ])
        await callback.message.answer(
            text=f"Управление residents:",
            reply_markup=keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Подтверждение удаления подрядчика
@router.callback_query(F.data.startswith("delete_contractor_"))
async def confirm_delete_contractor(callback: CallbackQuery):
    try:
        contractor_id = int(callback.data.split("_")[-1])
        await callback.message.answer(
            "Вы точно хотите удалить подрядчика?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_del_cont_yes_{contractor_id}")],
                [InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_del_cont_no_{contractor_id}")]
            ])
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Отмена удаления подрядчика
@router.callback_query(F.data.startswith("confirm_del_cont_no_"))
async def cancel_delete_contractor(callback: CallbackQuery):
    try:
        contractor_id = int(callback.data.split("_")[-1])
        # Возвращаемся к просмотру подрядчика
        await view_contractor_details(callback)
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


# Выполнение удаления подрядчика
@router.callback_query(F.data.startswith("confirm_del_cont_yes_"))
async def execute_delete_contractor(callback: CallbackQuery, state: FSMContext):
    try:
        contractor_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            # Удаляем связанные записи
            stmt1 = delete(ContractorRegistrationRequest).where(
                ContractorRegistrationRequest.contractor_id == contractor_id
            )
            stmt2 = delete(TemporaryPass).where(
                TemporaryPass.contractor_id == contractor_id
            )
            await session.execute(stmt1)
            await session.execute(stmt2)

            # Удаляем самого подрядчика
            stmt3 = delete(Contractor).where(Contractor.id == contractor_id)
            await session.execute(stmt3)
            await session.commit()

        await callback.message.answer("✅ Подрядчик удален")

        # Возвращаемся к списку подрядчиков
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить подрядчика", callback_data=f"add_contractors")],
            [InlineKeyboardButton(text="Список подрядчиков", callback_data="list_contractors")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
        ])
        await callback.message.answer(
            text=f"Управление contractors:",
            reply_markup=keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "list_managers")
async def show_managers_list(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Manager).where(Manager.status == True))
            managers = result.scalars().all()

            if not managers:
                await callback.answer("Нет зарегистрированных менеджеров")
                return

            buttons = []
            for manager in managers:
                button_text = f"{manager.id}_{manager.username}"
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."

                buttons.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_manager_{manager.id}"
                )])

            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="managers_manage"
            )])

            await callback.message.edit_text(
                "Список менеджеров:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data == "list_security")
async def show_security_list(callback: CallbackQuery):
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Security).where(Security.status == True))
            security_list = result.scalars().all()

            if not security_list:
                await callback.answer("Нет зарегистрированных сотрудников СБ")
                return

            buttons = []
            for security in security_list:
                button_text = f"{security.id}_{security.username}"
                if len(button_text) > 30:
                    button_text = button_text[:27] + "..."

                buttons.append([InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"view_security_{security.id}"
                )])

            buttons.append([InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="security_manage"
            )])

            await callback.message.edit_text(
                "Список сотрудников СБ:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
            )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("view_manager_"))
async def view_manager_details(callback: CallbackQuery):
    try:
        manager_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            manager = await session.get(Manager, manager_id)
            if not manager:
                await callback.answer("Менеджер не найден")
                return

            text = (
                f"ID: {manager.id}\n"
                f"Телефон: {manager.phone}\n"
                f"Username: @{manager.username}\n"
                f"TG ID: {manager.tg_id}\n"
                f"Время добавления: {manager.time_add_to_db}\n"
                f"Время регистрации: {manager.time_registration}\n"
                f"Статус: {'Активен' if manager.status else 'Неактивен'}"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_manager_{manager_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="list_managers")]
            ])

            await callback.message.answer(
                text=text,
                reply_markup=keyboard
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)

@router.callback_query(F.data.startswith("view_security_"))
async def view_security_details(callback: CallbackQuery):
    try:
        security_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            security = await session.get(Security, security_id)
            if not security:
                await callback.answer("Сотрудник СБ не найден")
                return

            text = (
                f"ID: {security.id}\n"
                f"Телефон: {security.phone}\n"
                f"Username: @{security.username}\n"
                f"TG ID: {security.tg_id}\n"
                f"Время добавления: {security.time_add_to_db}\n"
                f"Время регистрации: {security.time_registration}\n"
                f"Статус: {'Активен' if security.status else 'Неактивен'}"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_security_{security_id}")],
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="list_security")]
            ])

            await callback.message.answer(
                text=text,
                reply_markup=keyboard
            )
            await callback.answer()
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("delete_manager_"))
async def confirm_delete_manager(callback: CallbackQuery):
    try:
        manager_id = int(callback.data.split("_")[-1])
        await callback.message.answer(
            "Вы точно хотите удалить менеджера?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_manager_yes_{manager_id}")],
                [InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_delete_manager_no_{manager_id}")]
            ])
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)

@router.callback_query(F.data.startswith("delete_security_"))
async def confirm_delete_security(callback: CallbackQuery):
    try:
        security_id = int(callback.data.split("_")[-1])
        await callback.message.answer(
            "Вы точно хотите удалить сотрудника СБ?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_delete_security_yes_{security_id}")],
                [InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_delete_security_no_{security_id}")]
            ])
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("confirm_delete_manager_yes_"))
async def execute_delete_manager(callback: CallbackQuery, state: FSMContext):
    try:
        manager_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            stmt = delete(Manager).where(Manager.id == manager_id)
            await session.execute(stmt)
            await session.commit()

        await callback.message.answer("✅ Менеджер удален")

        # Возвращаемся в меню управления менеджерами
        data = await state.get_data()
        user_type = data['user_type']
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить менеджера", callback_data=f"add_{user_type}")],
            [InlineKeyboardButton(text="Список менеджеров", callback_data="list_managers")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
        ])

        await callback.message.answer(
            text=f"Управление {user_type}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)


@router.callback_query(F.data.startswith("confirm_delete_security_yes_"))
async def execute_delete_security(callback: CallbackQuery, state: FSMContext):
    try:
        security_id = int(callback.data.split("_")[-1])
        async with AsyncSessionLocal() as session:
            stmt = delete(Security).where(Security.id == security_id)
            await session.execute(stmt)
            await session.commit()

        await callback.message.answer("✅ Сотрудник СБ удален")

        # Возвращаемся в меню управления СБ
        data = await state.get_data()
        user_type = data['user_type']
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Добавить СБ", callback_data=f"add_{user_type}")],
            [InlineKeyboardButton(text="Список СБ", callback_data="list_security")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_manage")]
        ])

        await callback.message.answer(
            text=f"Управление {user_type}:",
            reply_markup=keyboard
        )
    except Exception as e:
        await bot.send_message(RAZRAB, f'{callback.from_user.id} - {str(e)}')
        await asyncio.sleep(0.05)

