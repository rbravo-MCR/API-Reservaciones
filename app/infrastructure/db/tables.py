from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, Numeric, String, Table

metadata = MetaData()

reservations = Table(
    "reservations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_code", String(50), nullable=False, unique=True),
    Column("supplier_id", Integer, nullable=False),
    Column("country_code", String(3), nullable=False),
    Column("pickup_office_id", Integer, nullable=False),
    Column("dropoff_office_id", Integer, nullable=False),
    Column("pickup_office_code", String(50)),
    Column("dropoff_office_code", String(50)),
    Column("car_category_id", Integer, nullable=False),
    Column("supplier_car_product_id", Integer),
    Column("acriss_code", String(10)),
    Column("pickup_datetime", DateTime, nullable=False),
    Column("dropoff_datetime", DateTime, nullable=False),
    Column("rental_days", Integer, nullable=False),
    Column("currency_code", String(3), nullable=False),
    Column("public_price_total", Numeric(12, 2), nullable=False),
    Column("supplier_cost_total", Numeric(12, 2), nullable=False),
    Column("taxes_total", Numeric(12, 2), nullable=False),
    Column("fees_total", Numeric(12, 2), nullable=False),
    Column("discount_total", Numeric(12, 2), nullable=False),
    Column("commission_total", Numeric(12, 2), nullable=False),
    Column("cashback_earned_amount", Numeric(12, 2), nullable=False),
    Column("status", String(32), nullable=False),
    Column("payment_status", String(32), nullable=False),
    Column("sales_channel_id", Integer, nullable=False),
    Column("traffic_source_id", Integer),
    Column("marketing_campaign_id", Integer),
    Column("affiliate_id", Integer),
    Column("utm_source", String(150)),
    Column("utm_medium", String(150)),
    Column("utm_campaign", String(255)),
    Column("utm_term", String(255)),
    Column("utm_content", String(255)),
    Column("booking_device", String(32)),
    Column("customer_ip", String(45)),
    Column("customer_user_agent", String(500)),
    Column("supplier_reservation_code", String(64)),
    Column("supplier_confirmed_at", DateTime),
    Column("lock_version", Integer, nullable=False, default=0),
)

reservation_contacts = Table(
    "reservation_contacts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_id", Integer, nullable=False),
    Column("reservation_code", String(50)),
    Column("contact_type", String(20), nullable=False),
    Column("full_name", String(255), nullable=False),
    Column("email", String(255), nullable=False),
    Column("phone", String(50)),
)

reservation_drivers = Table(
    "reservation_drivers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_id", Integer, nullable=False),
    Column("reservation_code", String(50)),
    Column("is_primary_driver", Integer, nullable=False),
    Column("first_name", String(150), nullable=False),
    Column("last_name", String(150), nullable=False),
    Column("email", String(255)),
    Column("phone", String(50)),
    Column("date_of_birth", String(20)),
    Column("driver_license_number", String(100)),
)

payments = Table(
    "payments",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_id", Integer, nullable=False),
    Column("reservation_code", String(50)),
    Column("provider", String(100), nullable=False),
    Column("status", String(32), nullable=False),
    Column("amount", Numeric(12, 2), nullable=False),
    Column("currency_code", String(3), nullable=False),
    Column("stripe_payment_intent_id", String(64)),
    Column("stripe_charge_id", String(64)),
    Column("stripe_event_id", String(64)),
)

idempotency_keys = Table(
    "idempotency_keys",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scope", String(32), nullable=False),
    Column("idem_key", String(128), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("response_json", JSON),
    Column("http_status", Integer),
    Column("reference_reservation_id", Integer),
    Column("reference_reservation_code", String(50)),
)

outbox_events = Table(
    "outbox_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_type", String(64), nullable=False),
    Column("aggregate_type", String(32), nullable=False),
    Column("aggregate_id", Integer),
    Column("aggregate_code", String(50)),
    Column("payload", JSON, nullable=False),
    Column("status", String(16), nullable=False, default="NEW"),
    Column("attempts", Integer, nullable=False, default=0),
    Column("next_attempt_at", DateTime),
    Column("locked_by", String(64)),
    Column("locked_at", DateTime),
    Column("lock_expires_at", DateTime),
    Column("created_at", DateTime),
    Column("updated_at", DateTime),
)

reservation_supplier_requests = Table(
    "reservation_supplier_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("reservation_id", Integer),
    Column("reservation_code", String(50)),
    Column("supplier_id", Integer),
    Column("request_type", String(32), nullable=False),
    Column("idem_key", String(128)),
    Column("attempt", Integer, nullable=False, default=0),
    Column("status", String(16), nullable=False),
    Column("http_status", Integer),
    Column("error_code", String(64)),
    Column("error_message", String(255)),
    Column("request_payload", JSON),
    Column("response_payload", JSON),
)

suppliers = Table(
    "suppliers",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("code", String(50), nullable=False, unique=True),
    Column("is_active", Integer, nullable=False, default=1),
)

offices = Table(
    "offices",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("code", String(50), nullable=False),
    Column("supplier_id", Integer, nullable=False),
    Column("country_code", String(3), nullable=False),
)

car_categories = Table(
    "car_categories",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("code", String(50), nullable=False, unique=True),
)

sales_channels = Table(
    "sales_channels",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("code", String(50), nullable=False, unique=True),
)

supplier_car_products = Table(
    "supplier_car_products",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("supplier_id", Integer, nullable=False),
    Column("car_category_id", Integer, nullable=False),
    Column("external_code", String(50), nullable=False),
)
