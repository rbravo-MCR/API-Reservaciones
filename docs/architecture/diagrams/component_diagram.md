# Component Diagram

```mermaid
graph TD
    Client[Client App] -->|HTTP/JSON| API[API Layer (FastAPI)]
    Stripe[Stripe] -->|Webhook| API

    subgraph "Application Core"
        API -->|Uses| UC_Create[CreateReservationUseCase]
        API -->|Uses| UC_Webhook[HandleStripeWebhookUseCase]
        API -->|Uses| UC_Outbox[ProcessOutboxUseCase]

        UC_Create -->|Port| RepoPort[ReservationRepository Interface]
        UC_Webhook -->|Port| RepoPort
        UC_Outbox -->|Port| RepoPort
        UC_Outbox -->|Port| GatewayPort[SupplierGateway Interface]
    end

    subgraph "Infrastructure"
        RepoAdapter[SQLAlchemy Repository] -->|Implements| RepoPort
        SupplierAdapter[Mock Supplier Adapter] -->|Implements| GatewayPort

        RepoAdapter -->|SQL| DB[(MySQL Database)]
        SupplierAdapter -->|HTTP| ExternalSupplier[External Supplier API]
    end
```
