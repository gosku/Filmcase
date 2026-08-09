import pkgutil
from collections.abc import Mapping, Sequence

import attrs
from celery import Task

from src.services import events


@attrs.frozen
class TaskNotFoundError(Exception):
    """
    Raised when *task_name* cannot be resolved to a Python object.
    """

    task_name: str


@attrs.frozen
class NotACeleryTaskError(Exception):
    """
    Raised when *task_name* resolves to an object that is not a Celery task.
    """

    task_name: str


def enqueue_task(*, task_name: str, kwargs: Mapping[str, object], queue: str) -> None:
    """
    Dispatch a Celery task by its dotted Python path to the given queue.

    Use this instead of calling task objects directly to avoid circular imports
    and to keep the application layer decoupled from task implementation details.

    :raises TaskNotFoundError: If *task_name* does not resolve to any Python object.
    :raises NotACeleryTaskError: If *task_name* resolves to something that is not a Celery task.
    """
    task = _resolve_task(task_name=task_name)

    task.apply_async(kwargs=dict(kwargs), queue=queue)

    events.publish_event(
        event_type=events.TASK_ENQUEUED,
        task_name=task_name,
        queue=queue,
    )


def enqueue_tasks(*, task_name: str, kwargs_list: Sequence[Mapping[str, object]], queue: str) -> int:
    """
    Dispatch the same Celery task once per entry in *kwargs_list*, and report how
    many were sent.

    Resolves the task once rather than per message, and publishes one event
    carrying the count rather than one per message. Dispatching happens before
    the caller can return, so a large import pays this cost up front: doing the
    per-message bookkeeping once keeps it off the critical path.

    :raises TaskNotFoundError: If *task_name* does not resolve to any Python object.
    :raises NotACeleryTaskError: If *task_name* resolves to something that is not a Celery task.
    """
    if not kwargs_list:
        return 0

    task = _resolve_task(task_name=task_name)

    for kwargs in kwargs_list:
        task.apply_async(kwargs=dict(kwargs), queue=queue)

    events.publish_event(
        event_type=events.TASK_ENQUEUED,
        task_name=task_name,
        queue=queue,
        count=len(kwargs_list),
    )
    return len(kwargs_list)


def _resolve_task(*, task_name: str) -> "Task[..., object]":
    try:
        task = pkgutil.resolve_name(task_name)
    except (AttributeError, ModuleNotFoundError, ValueError) as e:
        raise TaskNotFoundError(task_name=task_name) from e

    if not isinstance(task, Task):
        raise NotACeleryTaskError(task_name=task_name)

    return task


def is_celery_worker_available(*, timeout: float = 2.0) -> bool:
    """
    Return True if at least one Celery worker responds within *timeout* seconds.

    Uses a short-lived inspect ping to prevent blocking startup when the broker
    is unreachable.
    """
    from src.config.celery import app as celery_app  # local import avoids circular dependency

    result = celery_app.control.inspect(timeout=timeout).ping()
    return bool(result)
