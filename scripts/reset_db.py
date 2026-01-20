import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import text  # noqa: E402

from app.api.deps import engine  # noqa: E402
from app.infrastructure.db.tables import metadata  # noqa: E402


async def reset():
    async with engine.begin() as conn:
        # Disable FK checks to drop tables easily
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        for table in reversed(metadata.sorted_tables):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table.name}"))
            print(f"Dropped {table.name}")
            
        await conn.run_sync(metadata.create_all)
        print("Recreated all tables.")
        
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

if __name__ == "__main__":
    asyncio.run(reset())
