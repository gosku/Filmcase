import threading
from collections.abc import Callable

import structlog
from django import db

logger = structlog.get_logger("services.background")


def run_in_background(func: Callable[..., object], /, **kwargs: object) -> None:
    """
    Run ``func(**kwargs)`` in a daemon thread, detached from the calling request.

    The thread outlives the request that started it, so the caller returns
    immediately. Used in lite mode (no Celery) to keep a long sync off the request
    thread while still running server-side. Any unexpected error is logged to
    Sentry; the thread always closes its own database connection on exit, since
    Django only auto-closes connections at request boundaries.
    """

    def target() -> None:
        try:
            func(**kwargs)
        except Exception:
            logger.exception("Background task failed")
        finally:
            db.connection.close()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
