"""Exercise live and persistent timed status behavior."""

import asyncio
import os
import threading
from asyncio import CancelledError
from io import StringIO
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import patch

from rich.console import Console

from klogr import LoggingRich


class TimedStatusTests(TestCase):
    """Check timing, cleanup, and live rendering."""

    def test_live_clock_refreshes_without_a_status_update(self) -> None:
        """Advance the fake clock without calling update or polling a service."""
        output = StringIO()
        logger = LoggingRich(
            console=Console(
                file=output, force_terminal=True, force_interactive=True
            )
        )
        changed = threading.Event()
        current = 0.0

        def clock() -> float:
            if current == 7:
                changed.set()
            return current

        with (
            patch.dict(os.environ, {"TERM": "xterm-256color"}),
            patch("klogr.logger.monotonic", new=clock),
            logger.timed_status("Wait", completion=False),
        ):
            current = 7
            assert changed.wait(2)
        assert "07s" in output.getvalue()

    def test_text_updates_use_one_clock_and_are_throttled(self) -> None:
        """Keep the original start time across updates beyond 24 hours."""
        output = StringIO()
        logger = LoggingRich()
        times = iter((5.0, 6.0, 15.0, 15.0, 90066.0))
        with (
            patch("klogr.logger.monotonic", side_effect=lambda: next(times)),
            logger.route(output, terminal=False),
            logger.timed_status("Remote job", interval=10) as wait,
        ):
            wait.update("pending")
            wait.update("running", label="Render job", percent=60)
        lines = output.getvalue().splitlines()
        assert len(lines) == 2
        assert "running (60%)" in lines[0]
        assert lines[0].startswith("Render job")
        assert "completed (elapsed 01d : 01h : 01m : 01s)" in lines[1]
        assert "\x1b" not in output.getvalue()

    def test_failure_and_cancellation_preserve_the_original_error(
        self,
    ) -> None:
        """Report the correct outcome and propagate the same exception."""
        logger = LoggingRich()
        for error, outcome in (
            (RuntimeError("failed"), "failed"),
            (CancelledError(), "cancelled"),
        ):
            with self.subTest(outcome=outcome):
                output = StringIO()
                try:
                    with (
                        logger.route(output, terminal=False),
                        logger.timed_status("Job"),
                    ):
                        raise error
                except (RuntimeError, CancelledError) as caught:
                    received = caught
                else:
                    self.fail("The original exception did not propagate")
                assert received is error
                assert f"Job: {outcome}" in output.getvalue()
                assert "completed" not in output.getvalue()

    def test_nested_tty_statuses_share_progress_display(self) -> None:
        """Show nested waits and a progress bar in the same terminal."""
        output, persisted = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                file=output, force_terminal=True, force_interactive=True
            )
        )
        with (
            logger.route(persisted),
            logger.timed_status("Outer", interval=0) as wait,
            logger.timed_status("Inner"),
            logger.progress() as progress,
        ):
            progress.add_task("Decode", total=1, completed=1)
            wait.update("polling")
        assert "Outer" in output.getvalue()
        assert "Inner" in output.getvalue()
        assert "Decode" in output.getvalue()
        assert "Outer: polling" in persisted.getvalue()
        assert "\x1b" not in persisted.getvalue()

    def test_info_verbosity_suppresses_status_unless_enabled(self) -> None:
        """Respect logger verbosity and allow an explicit override."""
        output = StringIO()
        logger = LoggingRich(verbosity={"info": False})
        with logger.route(output, terminal=False):
            with logger.timed_status("Hidden", entry=True):
                pass
            with logger.timed_status("Visible", enabled=True):
                pass
        assert "Hidden" not in output.getvalue()
        assert "Visible: completed" in output.getvalue()


class ConcurrentTimedStatusTests(IsolatedAsyncioTestCase):
    """Verify overlapping waits on one logger and terminal."""

    async def test_overlapping_waits_can_finish_in_either_order(self) -> None:
        """Keep one display active until the final wait exits."""
        terminal = StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal, force_terminal=True, force_interactive=True
            )
        )
        second_entered, first_done = asyncio.Event(), asyncio.Event()

        async def first() -> None:
            with logger.timed_status("First"):
                await second_entered.wait()
            first_done.set()

        async def second() -> None:
            with logger.timed_status("Second") as wait:
                second_entered.set()
                await first_done.wait()
                wait.update("still running")

        await asyncio.wait_for(asyncio.gather(first(), second()), timeout=3)
        assert "First: completed" in terminal.getvalue()
        assert "Second: completed" in terminal.getvalue()
