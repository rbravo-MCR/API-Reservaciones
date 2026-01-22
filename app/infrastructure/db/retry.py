"""
Database retry utilities for handling transient failures.

Provides decorators and context managers for automatically retrying
database operations that fail due to deadlocks or other transient errors.
"""

import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar

from sqlalchemy.exc import DBAPIError, OperationalError

logger = logging.getLogger(__name__)

T = TypeVar('T')

# MySQL error codes
MYSQL_DEADLOCK_ERROR = "1213"
MYSQL_LOCK_WAIT_TIMEOUT = "1205"


def is_deadlock_error(error: Exception) -> bool:
    """
    Check if an exception is a deadlock error.

    Args:
        error: The exception to check

    Returns:
        True if the error is a deadlock that should be retried
    """
    if isinstance(error, (OperationalError, DBAPIError)):
        error_str = str(error)
        return MYSQL_DEADLOCK_ERROR in error_str or MYSQL_LOCK_WAIT_TIMEOUT in error_str
    return False


async def retry_on_deadlock(
    func: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 0.1,
) -> T:
    """
    Retry a function if it fails due to a database deadlock.

    Uses exponential backoff: base_delay * (2 ** attempt)

    Args:
        func: The async function to execute
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 0.1)

    Returns:
        The result of the function call

    Raises:
        The original exception if max attempts exceeded or non-deadlock error

    Example:
        async def update_reservation():
            async with session.begin():
                # ... database operations ...
                pass

        result = await retry_on_deadlock(update_reservation)
    """
    last_error = None

    for attempt in range(max_attempts):
        try:
            return await func()
        except Exception as e:
            last_error = e

            if not is_deadlock_error(e):
                # Not a deadlock, re-raise immediately
                raise

            if attempt < max_attempts - 1:
                # Calculate backoff delay
                delay = base_delay * (2 ** attempt)

                logger.warning(
                    "Database deadlock detected, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "max_attempts": max_attempts,
                        "retry_delay": delay,
                        "error": str(e),
                    }
                )

                await asyncio.sleep(delay)
            else:
                # Max attempts exceeded
                logger.error(
                    "Database deadlock persists after max retries",
                    extra={
                        "attempts": max_attempts,
                        "error": str(e),
                    }
                )
                raise

    # Should never reach here, but for type safety
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected state in retry_on_deadlock")


def with_deadlock_retry(max_attempts: int = 3, base_delay: float = 0.1):
    """
    Decorator to automatically retry async functions on database deadlocks.

    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 0.1)

    Example:
        @with_deadlock_retry(max_attempts=3)
        async def update_reservation(session: AsyncSession, code: str):
            async with session.begin():
                # ... database operations ...
                pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            async def execute():
                return await func(*args, **kwargs)

            return await retry_on_deadlock(execute, max_attempts, base_delay)

        return wrapper
    return decorator
