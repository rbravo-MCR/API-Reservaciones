import asyncio
from app.api.deps import AsyncSessionLocal
from sqlalchemy import text

async def check_db():
    async with AsyncSessionLocal() as session:
        # Consultar las últimas 3 reservas para ver el historial real
        result = await session.execute(text(
            "SELECT id, reservation_code, status, payment_status "
            "FROM reservations ORDER BY id DESC LIMIT 3"
        ))
        rows = result.fetchall()
        print("\n=== ESTADO ACTUAL DE LA BASE DE DATOS (AWS RDS) ===")
        print(f"{ 'ID':<5} | {'CÓDIGO':<15} | {'STATUS':<12} | {'PAYMENT':<10}")
        print("-" * 50)
        for row in rows:
            print(f"{row[0]:<5} | {row[1]:<15} | {row[2]:<12} | {row[3]:<10}")

if __name__ == "__main__":
    asyncio.run(check_db())