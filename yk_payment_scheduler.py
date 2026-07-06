"""Фоновая проверка pending-платежей ЮKassa."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from yk_payment_service import check_all_pending_yookassa_payments

logger = logging.getLogger(__name__)


def create_yookassa_payment_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_all_pending_yookassa_payments,
        "interval",
        minutes=1,
        id="yookassa_pending_payments",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


def start_yookassa_payment_scheduler() -> AsyncIOScheduler:
    scheduler = create_yookassa_payment_scheduler()
    scheduler.start()
    logger.info("YooKassa payment scheduler started (every 1 min)")
    return scheduler
