from unittest.mock import MagicMock, patch

import pytest
from celery import Task

from src.services import events
from src.services.workertasks import (
    NotACeleryTaskError,
    TaskNotFoundError,
    enqueue_task,
    enqueue_tasks,
    is_celery_worker_available,
)


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


class TestIsCeleryWorkerAvailable:
    def _patch_inspect(self, ping_return_value):
        mock_inspect = MagicMock()
        mock_inspect.ping.return_value = ping_return_value
        mock_control = MagicMock()
        mock_control.inspect.return_value = mock_inspect
        return patch("src.config.celery.app.control", mock_control)

    def test_returns_true_when_worker_responds(self):
        with self._patch_inspect({"celery@host": {"ok": "pong"}}):
            assert is_celery_worker_available() is True

    def test_returns_false_when_ping_returns_none(self):
        with self._patch_inspect(None):
            assert is_celery_worker_available() is False

    def test_returns_false_when_ping_returns_empty_dict(self):
        with self._patch_inspect({}):
            assert is_celery_worker_available() is False


class TestEnqueueTasks:
    def _task(self):
        task = MagicMock(spec=Task)
        return task

    def test_dispatches_one_message_per_entry(self):
        task = self._task()
        with patch("pkgutil.resolve_name", return_value=task):
            sent = enqueue_tasks(
                task_name="src.tasks.some_task",
                kwargs_list=[{"n": 1}, {"n": 2}, {"n": 3}],
                queue="default",
            )

        assert sent == 3
        assert task.apply_async.call_count == 3

    def test_resolves_the_task_once_however_many_messages(self):
        task = self._task()
        with patch("pkgutil.resolve_name", return_value=task) as resolve:
            enqueue_tasks(
                task_name="src.tasks.some_task",
                kwargs_list=[{"n": i} for i in range(50)],
                queue="default",
            )

        assert resolve.call_count == 1

    def test_publishes_one_event_carrying_the_count(self, captured_logs):
        task = self._task()
        with patch("pkgutil.resolve_name", return_value=task):
            enqueue_tasks(
                task_name="src.tasks.some_task",
                kwargs_list=[{"n": 1}, {"n": 2}],
                queue="default",
            )

        matching = [e for e in captured_logs if e.get("event_type") == events.TASK_ENQUEUED]
        assert len(matching) == 1
        assert matching[0]["count"] == 2

    def test_does_nothing_for_an_empty_list(self, captured_logs):
        with patch("pkgutil.resolve_name") as resolve:
            assert enqueue_tasks(task_name="src.tasks.some_task", kwargs_list=[], queue="default") == 0

        resolve.assert_not_called()
        assert [e for e in captured_logs if e.get("event_type") == events.TASK_ENQUEUED] == []

    def test_task_not_found_raises_task_not_found_error(self):
        with patch("pkgutil.resolve_name", side_effect=ModuleNotFoundError("no module")):
            with pytest.raises(TaskNotFoundError):
                enqueue_tasks(task_name="nope.some_task", kwargs_list=[{"n": 1}], queue="default")

    def test_object_is_not_celery_task_raises_not_a_celery_task_error(self):
        with patch("pkgutil.resolve_name", return_value=lambda: None):
            with pytest.raises(NotACeleryTaskError):
                enqueue_tasks(task_name="src.plain_function", kwargs_list=[{"n": 1}], queue="default")
