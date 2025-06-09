from db.models import engine, Base, PermanentPass
from sqlalchemy import text


async def run_migration():
    async with engine.begin() as conn:
        # Включить поддержку внешних ключей для SQLite
        await conn.execute(text("DROP TABLE permanent_pass"))

        # Создать временную таблицу с новой структурой
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                bind=sync_conn,
                tables=[PermanentPass.__table__]
            )
        )



if __name__ == "__main__":
    import asyncio

    asyncio.run(run_migration())