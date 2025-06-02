import asyncio
import logging

import handlers_admin
import handlers_admin_appeal
import handlers_admin_permanent_pass
import handlers_admin_search
import handlers_admin_statistic
import handlers_admin_temporary_pass
import handlers_contractor
import handlers_for_all
from aiogram import Dispatcher

import handlers_manager
import handlers_resident
import handlers_resident_appeal
import handlers_security
from bot import bot
from db.models import create_tables

logger = logging.getLogger(__name__)


async def main() -> None:
    await create_tables()
    logging.basicConfig(level=logging.INFO, format='%(filename)s:%(lineno)d %(levelname)-8s [%(asctime)s] - %(name)s - %(message)s')
    logging.info('Starting bot')

    dp = Dispatcher()
    dp.include_router(handlers_admin.router)
    dp.include_router(handlers_admin_appeal.router)
    dp.include_router(handlers_admin_search.router)
    dp.include_router(handlers_admin_statistic.router)
    dp.include_router(handlers_admin_permanent_pass.router)
    dp.include_router(handlers_admin_temporary_pass.router)
    dp.include_router(handlers_security.router)
    dp.include_router(handlers_manager.router)
    dp.include_router(handlers_contractor.router)
    dp.include_router(handlers_resident.router)
    dp.include_router(handlers_resident_appeal.router)
    dp.include_router(handlers_for_all.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

