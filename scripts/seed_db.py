import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from sqlalchemy import text  # noqa: E402

from app.api.deps import engine  # noqa: E402
from app.infrastructure.db.tables import metadata  # noqa: E402


async def seed():
    async with engine.begin() as conn:
        # Recreate tables
        await conn.run_sync(metadata.create_all)
        print("Recreated all tables.")

        # Seed data
        await conn.execute(
            text("INSERT INTO suppliers (id, name, code, is_active) VALUES (1, 'Avis', 'AVIS', 1)")
        )
        await conn.execute(
            text(
                "INSERT INTO offices (id, name, code, supplier_id, country_code) "
                "VALUES (1, 'Cancun Airport', 'CUN', 1, 'MX')"
            )
        )
        await conn.execute(
            text("INSERT INTO car_categories (id, name, code) VALUES (1, 'Economy', 'ECMN')")
        )
        await conn.execute(
            text("INSERT INTO sales_channels (id, name, code) VALUES (1, 'Web Direct', 'WEB')")
        )
        
        print("Seeded basic data.")

if __name__ == "__main__":
    asyncio.run(seed())
