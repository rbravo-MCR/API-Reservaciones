import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Connection string from .env.example
DATABASE_URL = "mysql+aiomysql://admin:2gexxdfc@car-rental-outlet.cqno6yuaulrd.us-east-1.rds.amazonaws.com:3306/cro_database"

async def test_connection():
    print(f"Testing connection to: {DATABASE_URL}")
    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(f"Connection Successful! Result: {result.scalar()}")
        await engine.dispose()
    except Exception as e:
        print(f"Connection Failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_connection())
