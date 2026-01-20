import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import text  # noqa: E402

from app.api.deps import engine  # noqa: E402
from app.infrastructure.db.tables import metadata  # noqa: E402


async def fix():
    async with engine.begin() as conn:
        # Disable FK checks
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        # Drop problematic tables
        await conn.execute(text("DROP TABLE IF EXISTS loyalty_transactions"))
        
        # Recreate all tables in metadata
        await conn.run_sync(metadata.create_all)
        print("Recreated all tables in metadata.")
        
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

if __name__ == "__main__":
    asyncio.run(fix())
