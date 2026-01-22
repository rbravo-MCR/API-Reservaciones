"""
Circuit Breaker configuration for external service calls.

This module provides pre-configured Circuit Breakers for external services
(Stripe, Suppliers) to prevent cascading failures and resource exhaustion.

Circuit Breaker Pattern:
- CLOSED: Normal operation, requests pass through
- OPEN: Too many failures, requests fail immediately
- HALF_OPEN: Testing if service recovered, limited requests allowed

Configuration:
- fail_max: Number of consecutive failures before opening circuit
- reset_timeout: Seconds to wait before attempting recovery (HALF_OPEN)
- exclude: Exceptions that don't count as failures
"""

import logging

from pybreaker import CircuitBreaker, CircuitBreakerError

logger = logging.getLogger(__name__)


# Stripe Circuit Breaker Configuration
stripe_breaker = CircuitBreaker(
    fail_max=5,  # Open circuit after 5 consecutive failures
    reset_timeout=60,  # Wait 60 seconds before attempting recovery
    name="stripe_circuit_breaker",
    listeners=[],  # Can add listeners for monitoring/alerting
)


# Supplier Circuit Breaker Configuration
# Using separate breakers per supplier would be ideal in production,
# but for this implementation we use a shared one for simplicity
supplier_breaker = CircuitBreaker(
    fail_max=5,  # Open circuit after 5 consecutive failures
    reset_timeout=60,  # Wait 60 seconds before attempting recovery
    name="supplier_circuit_breaker",
    listeners=[],
)


def log_circuit_state_change(breaker_name: str, old_state: str, new_state: str):
    """
    Log circuit breaker state changes for monitoring and alerting.

    In production, this should trigger alerts when circuits open.
    """
    logger.warning(
        f"Circuit breaker state changed",
        extra={
            "breaker_name": breaker_name,
            "old_state": old_state,
            "new_state": new_state,
        }
    )


# Add state change listeners
class CircuitBreakerListener:
    """Listener for circuit breaker state changes."""

    def __init__(self, name: str):
        self.name = name

    def state_change(self, breaker, old_state, new_state):
        """Called when circuit breaker state changes."""
        log_circuit_state_change(self.name, old_state.name, new_state.name)


stripe_breaker.add_listener(CircuitBreakerListener("stripe"))
supplier_breaker.add_listener(CircuitBreakerListener("supplier"))


__all__ = [
    "stripe_breaker",
    "supplier_breaker",
    "CircuitBreakerError",
]
