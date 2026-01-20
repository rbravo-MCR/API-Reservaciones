import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import text

from app.api.deps import engine


async def check():
    async with engine.connect() as conn:
        tables = ['suppliers', 'offices', 'car_categories', 'sales_channels']
        for t in tables:
            try:
                res = await conn.execute(text(f"SELECT COUNT(*) FROM {t}"))
                print(f"{t}: {res.scalar()} rows")
            except Exception as e:
                print(f"{t}: Error {e}")

if __name__ == "__main__":
    asyncio.run(check())
