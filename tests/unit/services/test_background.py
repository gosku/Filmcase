import threading
from unittest.mock import MagicMock, patch

from src.services.background import run_in_background


class TestRunInBackground:
    def test_runs_func_with_kwargs(self):
        done = threading.Event()
        captured: dict[str, object] = {}

        def work(*, a: int, b: int) -> None:
            captured["a"] = a
            captured["b"] = b
            done.set()

        with patch("src.services.background.db", MagicMock()):
            run_in_background(work, a=1, b=2)

        assert done.wait(timeout=2)
        assert captured == {"a": 1, "b": 2}

    def test_swallows_and_logs_unexpected_exception(self):
        logged = threading.Event()

        def boom() -> None:
            raise ValueError("nope")

        with (
            patch("src.services.background.logger") as mock_logger,
            patch("src.services.background.db", MagicMock()),
        ):
            mock_logger.exception.side_effect = lambda *a, **k: logged.set()
            run_in_background(boom)
            assert logged.wait(timeout=2)

        mock_logger.exception.assert_called_once()

    def test_closes_db_connection_on_exit(self):
        closed = threading.Event()
        fake_db = MagicMock()
        fake_db.connection.close.side_effect = lambda: closed.set()

        with patch("src.services.background.db", fake_db):
            run_in_background(lambda: None)
            assert closed.wait(timeout=2)

        fake_db.connection.close.assert_called_once()
