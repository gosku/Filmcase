from unittest.mock import MagicMock, patch

import pytest
from celery import Task

from src.services import events
from src.services.workertasks import NotACeleryTaskError, TaskNotFoundError, enqueue_task


class TestEnqueueTask:
    def test_task_not_found_raises_task_not_found_error(self):
        with patch("pkgutil.resolve_name", side_effect=ModuleNotFoundError("no module")):
            with pytest.raises(TaskNotFoundError) as exc_info:
                enqueue_task(
                    task_name="nonexistent.module.some_task",
                    kwargs={"foo": "bar"},
                    queue="default",
                )
        assert exc_info.value.task_name == "nonexistent.module.some_task"

    def test_object_is_not_celery_task_raises_not_a_celery_task_error(self):
        with patch("pkgutil.resolve_name", return_value=lambda: None):
            with pytest.raises(NotACeleryTaskError) as exc_info:
                enqueue_task(
                    task_name="src.some.module.plain_function",
                    kwargs={},
                    queue="default",
                )
        assert exc_info.value.task_name == "src.some.module.plain_function"

    def test_valid_task_calls_apply_async_and_publishes_event(self):
        fake_task = MagicMock(spec=Task)

        with (
            patch("pkgutil.resolve_name", return_value=fake_task),
            patch.object(events, "publish_event") as mock_publish,
        ):
            enqueue_task(
                task_name="src.interfaces.tasks.process_image_task",
                kwargs={"image_path": "/some/image.jpg"},
                queue="celery",
            )

        fake_task.apply_async.assert_called_once_with(
            kwargs={"image_path": "/some/image.jpg"},
            queue="celery",
        )
        mock_publish.assert_called_once_with(
            event_type=events.TASK_ENQUEUED,
            task_name="src.interfaces.tasks.process_image_task",
            queue="celery",
        )
