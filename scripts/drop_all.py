import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import text

from app.api.deps import engine


async def drop_everything():
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        # Get all tables
        res = await conn.execute(text("SHOW TABLES"))
        tables = [row[0] for row in res]
        
        for table in tables:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            print(f"Dropped {table}")
            
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

if __name__ == "__main__":
    asyncio.run(drop_everything())
