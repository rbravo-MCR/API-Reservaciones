# ADR 001: Hexagonal Architecture

## Status

Accepted

## Context

We are building a Reservation System that needs to integrate with multiple external providers (Stripe, Hertz, Budget, etc.) and support different delivery mechanisms (API, CLI, Workers). We need a way to isolate the core business logic from these external concerns to ensure testability and maintainability.

## Decision

We will use **Hexagonal Architecture (Ports and Adapters)**.

- **Domain Layer**: Contains the core business logic and entities (`Reservation`, `OutboxEvent`). It has no dependencies on outer layers.
- **Application Layer**: Contains Use Cases (`CreateReservation`, `ProcessOutbox`) that orchestrate the domain logic. It defines Interfaces (Ports) for external dependencies.
- **Infrastructure Layer**: Contains the implementation of the interfaces (Adapters) for Database (`SQLAlchemy`), Payment (`Stripe`), and Suppliers (`Mock`).
- **API Layer**: The entry point (Driver Adapter) using FastAPI.

## Consequences

### Positive

- **Testability**: We can easily mock external dependencies (Suppliers, DB) to test business logic in isolation.
- **Flexibility**: We can switch providers (e.g., Stripe to PayPal) by creating a new Adapter without changing the core logic.
- **Maintainability**: Clear separation of concerns.

### Negative

- **Complexity**: Adds more layers and boilerplate code (Interfaces, DTOs) compared to a simple MVC or CRUD architecture.
