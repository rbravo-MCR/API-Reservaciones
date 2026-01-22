from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AsyncSessionLocal
from app.application.use_cases.create_reservation_intent import CreateReservationIntentUseCase
from app.application.use_cases.get_receipt import GetReceiptUseCase
from app.application.use_cases.handle_stripe_webhook import HandleStripeWebhookUseCase
from app.application.use_cases.pay_reservation import PayReservationUseCase
from app.application.use_cases.process_outbox_book_supplier import ProcessOutboxBookSupplierUseCase
from app.config import Settings, get_settings
from app.infrastructure.db.queries.receipt_query_sql import ReceiptQuerySQL
from app.infrastructure.db.repositories.idempotency_repo_sql import IdempotencyRepoSQL
from app.infrastructure.db.repositories.outbox_repo_sql import OutboxRepoSQL
from app.infrastructure.db.repositories.payment_repo_sql import PaymentRepoSQL
from app.infrastructure.db.repositories.reservation_repo_sql import ReservationRepoSQL
from app.infrastructure.db.repositories.supplier_request_repo_sql import SupplierRequestRepoSQL
from app.infrastructure.db.transaction_manager import SQLAlchemyTransactionManager
from app.infrastructure.gateways.factory import SupplierGatewayFactory
from app.infrastructure.gateways.stripe_gateway_real import StripeGatewayReal
from app.infrastructure.gateways.supplier_gateway_http import SupplierGatewayHTTP
from app.infrastructure.gateways.supplier_gateway_selector import SupplierGatewaySelector
from app.infrastructure.in_memory.idempotency_repo import InMemoryIdempotencyRepo
from app.infrastructure.in_memory.outbox_repo import InMemoryOutboxRepo
from app.infrastructure.in_memory.payment_repo import InMemoryPaymentRepo
from app.infrastructure.in_memory.receipt_query import InMemoryReceiptQuery
from app.infrastructure.in_memory.reservation_repo import InMemoryReservationRepo
from app.infrastructure.in_memory.stripe_gateway import StubStripeGateway
from app.infrastructure.in_memory.supplier_gateway import StubSupplierGateway
from app.infrastructure.in_memory.supplier_request_repo import InMemorySupplierRequestRepo
from app.infrastructure.in_memory.transaction_manager import NoopTransactionManager


async def get_session(settings: Settings = Depends(get_settings)) -> AsyncSession | None:
    if settings.use_in_memory:
        yield None
        return
    async with AsyncSessionLocal() as session:
        yield session


@lru_cache(maxsize=1)
def _in_memory_bundle():
    idempotency_repo = InMemoryIdempotencyRepo()
    reservation_repo = InMemoryReservationRepo()
    payment_repo = InMemoryPaymentRepo()
    outbox_repo = InMemoryOutboxRepo()
    supplier_request_repo = InMemorySupplierRequestRepo()
    stripe_gateway = StubStripeGateway()
    tx_manager = NoopTransactionManager()
    receipt_query = InMemoryReceiptQuery(
        reservation_repo=reservation_repo,
        payment_repo=payment_repo,
        supplier_request_repo=supplier_request_repo,
    )
    supplier_selector = SupplierGatewaySelector(default_gateway=StubSupplierGateway())
    return {
        "idempotency_repo": idempotency_repo,
        "reservation_repo": reservation_repo,
        "payment_repo": payment_repo,
        "outbox_repo": outbox_repo,
        "supplier_request_repo": supplier_request_repo,
        "stripe_gateway": stripe_gateway,
        "tx_manager": tx_manager,
        "receipt_query": receipt_query,
        "supplier_selector": supplier_selector,
    }


def _generate_reservation_code() -> str:
    from uuid import uuid4

    return f"RES-{uuid4().hex[:8].upper()}"


def get_use_cases(
    settings: Settings = Depends(get_settings),
    session: AsyncSession | None = Depends(get_session),
):
    if settings.use_in_memory:
        bundle = _in_memory_bundle()
        try:
            # Exponer repo para pruebas que acceden via router (compatibilidad)
            import app.api.routers.reservations as reservations_router

            reservations_router._reservation_repo = bundle["reservation_repo"]
        except Exception:
            pass
        return {
            "create_reservation": CreateReservationIntentUseCase(
                reservation_repo=bundle["reservation_repo"],
                idempotency_repo=bundle["idempotency_repo"],
                transaction_manager=bundle["tx_manager"],
                code_generator=_generate_reservation_code,
            ),
            "pay_reservation": PayReservationUseCase(
                reservation_repo=bundle["reservation_repo"],
                payment_repo=bundle["payment_repo"],
                idempotency_repo=bundle["idempotency_repo"],
                stripe_gateway=bundle["stripe_gateway"],
                outbox_repo=bundle["outbox_repo"],
                transaction_manager=bundle["tx_manager"],
            ),
            "handle_webhook": HandleStripeWebhookUseCase(
                payment_repo=bundle["payment_repo"],
                reservation_repo=bundle["reservation_repo"],
                outbox_repo=bundle["outbox_repo"],
                stripe_gateway=bundle["stripe_gateway"],
                stripe_webhook_secret=settings.stripe_webhook_secret,
            ),
            "get_receipt": GetReceiptUseCase(receipt_query=bundle["receipt_query"]),
            "process_outbox": ProcessOutboxBookSupplierUseCase(
                outbox_repo=bundle["outbox_repo"],
                reservation_repo=bundle["reservation_repo"],
                supplier_gateway_selector=bundle["supplier_selector"],
                supplier_request_repo=bundle["supplier_request_repo"],
            ),
        }

    if not session:
        raise RuntimeError("DB session not available")

    idempotency_repo = IdempotencyRepoSQL(session)
    reservation_repo = ReservationRepoSQL(session)
    payment_repo = PaymentRepoSQL(session)
    outbox_repo = OutboxRepoSQL(session)
    supplier_request_repo = SupplierRequestRepoSQL(session)
    stripe_gateway = StripeGatewayReal(api_key=settings.stripe_api_key)
    tx_manager = SQLAlchemyTransactionManager(session)
    receipt_query = ReceiptQuerySQL(session)
    default_supplier_gateway = StubSupplierGateway()
    
    # Configuración preliminar para la Factory (se debe expandir Settings en el futuro)
    factory_config = {
        "avis": {"endpoint": settings.supplier_base_url},
        "europcargroup": {"endpoint": settings.supplier_base_url},
        "americagroup": {
            "endpoint": settings.americagroup_endpoint,
            "requestor_id": settings.americagroup_requestor_id,
            "timeout_seconds": settings.americagroup_timeout_seconds,
            "retry_times": settings.americagroup_retry_times,
            "retry_sleep_ms": settings.americagroup_retry_sleep_ms,
        },
        # Placeholders para nuevos proveedores (requieren variables de entorno reales)
        "hertzargentina": {"base_url": "https://hertz.test"},
        "infinity": {"endpoint": "https://infinity.test"},
        "localiza": {"endpoint": "https://localiza.test"},
        "mexgroup": {"endpoint": "https://mex.test"},
        "nationalgroup": {"endpoint": "https://national.test"},
        "nizacars": {"base_url": "https://niza.test"},
        "noleggiare": {"endpoint": "https://noleggiare.test"},
    }
    
    gateway_factory = SupplierGatewayFactory(config=factory_config)
    
    selector = SupplierGatewaySelector(
        default_gateway=default_supplier_gateway,
        factory=gateway_factory
    )
    
    if settings.supplier_base_url:
        selector.register(
            supplier_id=0,  # fallback mapping; real mappings deberían ser específicos
            country_code="*",
            gateway=SupplierGatewayHTTP(
                base_url=settings.supplier_base_url,
                timeout_seconds=settings.supplier_timeout_seconds,
            ),
        )
    if settings.americagroup_endpoint:
        selector.register(
            supplier_id=32,  # America Group
            country_code="MX",
            gateway=AmericaGroupGateway(
                endpoint=settings.americagroup_endpoint,
                requestor_id=settings.americagroup_requestor_id or "13",
                timeout_seconds=settings.americagroup_timeout_seconds,
                retry_times=settings.americagroup_retry_times,
                retry_sleep_ms=settings.americagroup_retry_sleep_ms,
            ),
        )

    return {
        "create_reservation": CreateReservationIntentUseCase(
            reservation_repo=reservation_repo,
            idempotency_repo=idempotency_repo,
            transaction_manager=tx_manager,
            code_generator=_generate_reservation_code,
        ),
        "pay_reservation": PayReservationUseCase(
            reservation_repo=reservation_repo,
            payment_repo=payment_repo,
            idempotency_repo=idempotency_repo,
            stripe_gateway=stripe_gateway,
            outbox_repo=outbox_repo,
            transaction_manager=tx_manager,
        ),
        "handle_webhook": HandleStripeWebhookUseCase(
            payment_repo=payment_repo,
            reservation_repo=reservation_repo,
            outbox_repo=outbox_repo,
            stripe_gateway=stripe_gateway,
            stripe_webhook_secret=settings.stripe_webhook_secret,
        ),
        "get_receipt": GetReceiptUseCase(receipt_query=receipt_query),
        "process_outbox": ProcessOutboxBookSupplierUseCase(
            outbox_repo=outbox_repo,
            reservation_repo=reservation_repo,
            supplier_gateway_selector=selector,
            supplier_request_repo=supplier_request_repo,
        ),
    }
