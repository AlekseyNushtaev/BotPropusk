"""Проверка оплаты грузового пропуска (ЮKassa)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot import bot
from config import RAZRAB, YUKASSA_SECRET_KEY, YUKASSA_SHOP_ID
from yk_payment_service import PaymentCheckResult, try_process_pending_payment

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(F.data.startswith("yk_check_"))
async def yk_check_truck_payment(callback: CallbackQuery) -> None:
    uid = callback.from_user.id
    try:
        pay_row_id = int((callback.data or "").split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный запрос", show_alert=True)
        return

    if not YUKASSA_SHOP_ID or not YUKASSA_SECRET_KEY:
        await callback.answer("Оплата недоступна", show_alert=True)
        return

    try:
        result = await try_process_pending_payment(pay_row_id, owner_tg_id=uid)

        if result == PaymentCheckResult.NOT_FOUND:
            await callback.answer("Платёж не найден", show_alert=True)
        elif result == PaymentCheckResult.PASS_NOT_FOUND:
            await callback.answer("Пропуск не найден", show_alert=True)
        elif result == PaymentCheckResult.NO_ACCESS:
            await callback.answer("Нет доступа", show_alert=True)
        elif result == PaymentCheckResult.ALREADY_APPROVED:
            await callback.answer("Пропуск уже подтверждён", show_alert=True)
        elif result == PaymentCheckResult.NOT_AWAITING_PAYMENT:
            await callback.answer("Заявка не ожидает оплаты", show_alert=True)
        elif result == PaymentCheckResult.CANCELED:
            await callback.answer("Срок оплаты истёк, создайте новую заявку", show_alert=True)
        elif result == PaymentCheckResult.YK_UNAVAILABLE:
            await callback.answer("Не удалось проверить оплату, попробуйте позже", show_alert=True)
        elif result == PaymentCheckResult.STILL_PENDING:
            await callback.answer("Оплаты пока не было — нажмите «Оплатить»", show_alert=True)
        elif result == PaymentCheckResult.SUCCEEDED:
            await callback.answer("Оплата получена, пропуск подтверждён")
    except Exception as e:
        logger.exception("yk_check_truck_payment")
        await bot.send_message(RAZRAB, text=f"{uid} - {e!s}")
        await asyncio.sleep(0.05)
        await callback.answer("Ошибка", show_alert=True)
