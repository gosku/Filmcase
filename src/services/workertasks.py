import pkgutil
from collections.abc import Mapping

import attrs
from celery import Task

from src.services import events


@attrs.frozen
class TaskNotFoundError(Exception):
    """Raised when *task_name* cannot be resolved to a Python object."""

    task_name: str


@attrs.frozen
class NotACeleryTaskError(Exception):
    """Raised when *task_name* resolves to an object that is not a Celery task."""

    task_name: str


def enqueue_task(*, task_name: str, kwargs: Mapping[str, object], queue: str) -> None:
    """Dispatch a Celery task by its dotted Python path to the given queue.

    Use this instead of calling task objects directly to avoid circular imports
    and to keep the application layer decoupled from task implementation details.

    :raises TaskNotFoundError: If *task_name* does not resolve to any Python object.
    :raises NotACeleryTaskError: If *task_name* resolves to something that is not a Celery task.
    """
    try:
        task = pkgutil.resolve_name(task_name)
    except (AttributeError, ModuleNotFoundError, ValueError) as e:
        raise TaskNotFoundError(task_name=task_name) from e

    if not isinstance(task, Task):
        raise NotACeleryTaskError(task_name=task_name)

    task.apply_async(kwargs=dict(kwargs), queue=queue)

    events.publish_event(
        event_type=events.TASK_ENQUEUED,
        task_name=task_name,
        queue=queue,
    )
