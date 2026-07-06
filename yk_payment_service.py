"""Проверка и подтверждение платежей ЮKassa (кнопка и фоновая задача)."""

from __future__ import annotations

import asyncio
import datetime
import enum
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot import bot
from config import YUKASSA_SECRET_KEY, YUKASSA_SHOP_ID
from db.models import (
    AsyncSessionLocal,
    Contractor,
    Resident,
    TempPassYooKassaPayment,
    TemporaryPass,
)
from db.util import get_active_admins_managers_sb_tg_ids, text_warning
from handlers.handlers_admin_user_management import admin_reply_keyboard
from temp_pass_staff_notify import build_auto_approved_staff_notice
from yookassa_api import get_payment_status

logger = logging.getLogger(__name__)

PAYMENT_PENDING_TTL = datetime.timedelta(days=10)


class PaymentCheckResult(enum.Enum):
    NOT_FOUND = "not_found"
    PASS_NOT_FOUND = "pass_not_found"
    NO_ACCESS = "no_access"
    ALREADY_APPROVED = "already_approved"
    NOT_AWAITING_PAYMENT = "not_awaiting_payment"
    CANCELED = "canceled"
    YK_UNAVAILABLE = "yk_unavailable"
    STILL_PENDING = "still_pending"
    SUCCEEDED = "succeeded"


def temp_pass_followup_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оформить временный пропуск", callback_data="create_temporary_pass")],
            [InlineKeyboardButton(text="Назад", callback_data="back_to_main_menu")],
        ]
    )


async def _load_owner(
    session,
    tp: TemporaryPass,
) -> tuple[Resident | None, Contractor | None]:
    resident = None
    contractor = None
    if tp.owner_type == "resident" and tp.resident_id:
        resident = await session.get(Resident, tp.resident_id)
    elif tp.owner_type == "contractor" and tp.contractor_id:
        contractor = await session.get(Contractor, tp.contractor_id)
    return resident, contractor


def _owns_pass(
    tp: TemporaryPass,
    resident: Resident | None,
    contractor: Contractor | None,
    owner_tg_id: int,
) -> bool:
    if tp.owner_type == "resident" and resident and resident.tg_id == owner_tg_id:
        return True
    if tp.owner_type == "contractor" and contractor and contractor.tg_id == owner_tg_id:
        return True
    return False


async def send_payment_success_notifications(
    *,
    tp: TemporaryPass,
    pay: TempPassYooKassaPayment,
    resident: Resident | None,
    contractor: Contractor | None,
) -> None:
    car_num = (tp.car_number or "").upper()
    kb = temp_pass_followup_kb()
    chat_id = None
    if resident and resident.tg_id:
        chat_id = resident.tg_id
    elif contractor and contractor.tg_id:
        chat_id = contractor.tg_id

    if chat_id:
        try:
            await bot.send_message(
                chat_id,
                f"✅ Ваш временный пропуск одобрен на машину с номером {car_num}",
                reply_markup=kb,
            )
            await bot.send_message(chat_id, text_warning)
        except Exception:
            logger.exception("Failed to notify payer tg_id=%s about pass %s", chat_id, tp.id)

    paid_rub = max(0, (pay.amount_kopeks or 0) // 100)
    for tg_id in await get_active_admins_managers_sb_tg_ids():
        try:
            if tp.owner_type == "resident" and resident:
                hdr = f"Пропуск от резидента {resident.fio} одобрен автоматически"
            elif tp.owner_type == "contractor" and contractor:
                hdr = (
                    f"Пропуск от подрядчика {contractor.fio}, "
                    f"{contractor.company or ''} — {contractor.position or ''} одобрен автоматически"
                )
            else:
                hdr = f"Временный пропуск №{tp.id} одобрен автоматически после оплаты"
            note = build_auto_approved_staff_notice(
                header_line=hdr,
                vehicle_type=tp.vehicle_type,
                weight_category=tp.weight_category,
                length_category=tp.length_category,
                cargo_type=tp.cargo_type,
                car_brand=tp.car_brand,
                car_model=None,
                car_number=tp.car_number,
                visit_date=tp.visit_date,
                purpose=tp.purpose,
                payment_rubles=paid_rub,
            )
            await bot.send_message(tg_id, text=note, reply_markup=admin_reply_keyboard)
            await asyncio.sleep(0.05)
        except Exception:
            pass


async def apply_successful_payment(
    session,
    pay: TempPassYooKassaPayment,
    tp: TemporaryPass,
    *,
    now: datetime.datetime | None = None,
) -> tuple[Resident | None, Contractor | None]:
    now = now or datetime.datetime.now()
    resident, contractor = await _load_owner(session, tp)
    pay.status = "succeeded"
    pay.paid_at = now
    tp.status = "approved"
    tp.time_registration = now
    await session.commit()
    return resident, contractor


async def try_process_pending_payment(
    pay_row_id: int,
    *,
    owner_tg_id: int | None = None,
) -> PaymentCheckResult:
    if not YUKASSA_SHOP_ID or not YUKASSA_SECRET_KEY:
        return PaymentCheckResult.YK_UNAVAILABLE

    async with AsyncSessionLocal() as session:
        pay = await session.get(TempPassYooKassaPayment, pay_row_id)
        if not pay:
            return PaymentCheckResult.NOT_FOUND

        tp = await session.get(TemporaryPass, pay.temporary_pass_id)
        if not tp:
            return PaymentCheckResult.PASS_NOT_FOUND

        resident, contractor = await _load_owner(session, tp)

        if owner_tg_id is not None and not _owns_pass(tp, resident, contractor, owner_tg_id):
            return PaymentCheckResult.NO_ACCESS

        if tp.status == "approved":
            return PaymentCheckResult.ALREADY_APPROVED

        if pay.status == "canceled":
            return PaymentCheckResult.CANCELED

        if tp.status != "awaiting_payment":
            return PaymentCheckResult.NOT_AWAITING_PAYMENT

        if pay.status != "pending":
            return PaymentCheckResult.STILL_PENDING

        now = datetime.datetime.now()
        yk_status = await get_payment_status(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY, pay.yookassa_payment_id)

        if yk_status == "succeeded":
            resident, contractor = await apply_successful_payment(session, pay, tp, now=now)
            await send_payment_success_notifications(tp=tp, pay=pay, resident=resident, contractor=contractor)
            return PaymentCheckResult.SUCCEEDED

        if yk_status is None:
            return PaymentCheckResult.YK_UNAVAILABLE

        if now - pay.created_at > PAYMENT_PENDING_TTL:
            pay.status = "canceled"
            await session.commit()
            return PaymentCheckResult.CANCELED

        return PaymentCheckResult.STILL_PENDING


async def check_all_pending_yookassa_payments() -> None:
    if not YUKASSA_SHOP_ID or not YUKASSA_SECRET_KEY:
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TempPassYooKassaPayment.id).where(TempPassYooKassaPayment.status == "pending")
        )
        pay_ids = list(result.scalars())

    for pay_id in pay_ids:
        try:
            outcome = await try_process_pending_payment(pay_id)
            if outcome == PaymentCheckResult.SUCCEEDED:
                logger.info("YooKassa payment %s confirmed in background", pay_id)
            elif outcome == PaymentCheckResult.CANCELED:
                logger.info("YooKassa payment %s canceled (expired)", pay_id)
        except Exception:
            logger.exception("Background YooKassa check failed for payment %s", pay_id)
