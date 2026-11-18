"""Exercise scoped output through the public logger API."""

import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import IsolatedAsyncioTestCase, TestCase

from rich.console import Console, ConsoleOptions, RenderResult

from klogr import LoggingRich, LoggingTable, get_logger


class _DestinationLabel:
    def __rich_console__(
        self, console: Console, _options: ConsoleOptions
    ) -> RenderResult:
        yield "terminal view" if console.is_terminal else "file view"


class LoggerRoutingTests(TestCase):
    """Exercise terminal and plain text routes and their lifetimes."""

    def test_forced_json_uses_the_callers_source_location(self) -> None:
        """Emit forced messages even with both levels disabled."""
        run = subprocess.run(
            [
                sys.executable,
                "-c",
                "from klogr import get_logger\n"
                "logger = get_logger({'info': False, 'log': False})\n"
                "logger.info_once('forced info', force=True, indent=None)\n"
                "logger.log('forced log', force=True, indent=None)\n",
            ],
            env=os.environ | {"JSON_FORMATTER": "True"},
            capture_output=True,
            text=True,
            check=True,
        )
        records = [json.loads(line) for line in run.stdout.splitlines()]
        assert [
            (record["message"], record["filename"]) for record in records
        ] == [
            ("forced info", "<string>:3"),
            ("forced log", "<string>:4"),
        ]

    def test_table_can_be_constructed_and_rendered(self) -> None:
        """Render the columns and values from a keyword-initialized table."""
        stream = StringIO()
        logger = LoggingRich(console=Console(file=stream))
        logger.table(
            LoggingTable(
                title="Run summary",
                columns=["Phase"],
                colors=["cyan"],
                rows=[["Complete"]],
            )
        )
        rendered = stream.getvalue()
        assert "Run summary" in rendered
        assert "Phase" in rendered
        assert "Complete" in rendered

    def test_distinct_destinations_render_once_and_preserve_json(self) -> None:
        """Keep stdout parseable while styling stderr and writing plain text."""
        stdout, stderr, log_file = StringIO(), StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                stderr=True,
                force_terminal=True,
                color_system="standard",
                no_color=False,
            )
        )
        with (
            redirect_stdout(stdout),
            redirect_stderr(stderr),
            logger.route(stderr, log_file, log_file),
        ):
            assert sys.stdout is stdout
            assert sys.stderr is stderr
            logger.print("processed", style="red", force=True)
            print(json.dumps({"ok": True}))
        assert json.loads(stdout.getvalue()) == {"ok": True}
        assert stderr.getvalue().count("processed") == 1
        assert "\x1b[" in stderr.getvalue()
        assert log_file.getvalue() == "processed\n"
        assert not log_file.closed

    def test_rich_rendering_uses_each_destination(self) -> None:
        """Allow Rich renderables to adapt to each output destination."""
        terminal, log_file = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(file=terminal, force_terminal=True, no_color=True)
        )
        with logger.route(log_file):
            logger.print(_DestinationLabel(), force=True)
        assert terminal.getvalue() == "terminal view\n"
        assert log_file.getvalue() == "file view\n"

    def test_route_deduplicates_current_stderr_after_redirection(self) -> None:
        """Track terminal redirections while keeping explicit destinations."""
        stderr, log_file = StringIO(), StringIO()
        logger = get_logger(stderr=True)
        with redirect_stderr(log_file), logger.route(log_file):
            with redirect_stderr(stderr):
                logger.print("two destinations", force=True)
            logger.print("one destination", force=True)
        assert stderr.getvalue() == "two destinations\n"
        assert log_file.getvalue() == "two destinations\none destination\n"

    def test_track_uses_requested_console(self) -> None:
        """Keep the progress display on the caller's preferred console."""
        terminal, progress_output = StringIO(), StringIO()
        logger = LoggingRich(console=Console(file=terminal))

        def items() -> Iterator[int]:
            yield 1
            yield 2

        tracked = logger.track(
            items(),
            total=2,
            description="Processing",
            console=Console(file=progress_output),
        )
        assert list(tracked) == [1, 2]
        assert "Processing" in progress_output.getvalue()
        assert "2/2" in progress_output.getvalue()
        assert terminal.getvalue() == ""

    def test_nested_file_only_route_restores_outer_on_error(self) -> None:
        """Replace the outer route and resume it when the inner scope exits."""
        terminal, outer, inner = StringIO(), StringIO(), StringIO()
        logger = LoggingRich(console=Console(file=terminal))
        with logger.route(outer, terminal=False):
            logger.print("before", force=True)
            try:
                with logger.route(inner, terminal=False):
                    logger.info("inner only", force=True)
                    message = "interrupted"
                    raise RuntimeError(message)
            except RuntimeError:
                pass
            logger.print("after", force=True)
        logger.print("terminal only", force=True)
        assert outer.getvalue() == "before\nafter\n"
        assert "inner only" in inner.getvalue()
        assert terminal.getvalue() == "terminal only\n"

    def test_timed_messages_follow_file_only_route(self) -> None:
        """Send start and completion diagnostics to the scoped file."""
        terminal, log_file = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(file=terminal),
            verbosity={"info": True, "success": True, "log": True},
        )
        with logger.route(log_file, terminal=False), logger.timed("stage"):
            pass
        assert log_file.getvalue().count("stage") == 2
        assert terminal.getvalue() == ""

    def test_scopes_with_no_files_can_route_to_stderr(self) -> None:
        """Use the selected stderr console for a terminal-only route."""
        stdout, stderr = StringIO(), StringIO()
        logger = get_logger(stderr=True)
        with redirect_stdout(stdout), redirect_stderr(stderr), logger.route():
            logger.print("diagnostic", force=True)
            print(json.dumps({"records": 12}))
        assert json.loads(stdout.getvalue()) == {"records": 12}
        assert stderr.getvalue() == "diagnostic\n"


class ConcurrentRoutingTests(IsolatedAsyncioTestCase):
    """Exercise independent routes on the same cached logger."""

    async def test_concurrent_routes_and_cancellation_restore_scope(
        self,
    ) -> None:
        """Keep sibling messages isolated and restore the cancelled task's route."""
        first, second, fallback = StringIO(), StringIO(), StringIO()
        first_entered = asyncio.Event()
        second_finished = asyncio.Event()
        logger = get_logger(stderr=True)

        async def cancel_me() -> None:
            try:
                with logger.route(first, terminal=False):
                    logger.print("first", force=True)
                    first_entered.set()
                    await asyncio.Event().wait()
            finally:
                logger.print("restored", force=True)

        async def finish() -> None:
            with logger.route(second, terminal=False):
                await first_entered.wait()
                logger.print("second", force=True)
            second_finished.set()

        with logger.route(fallback, terminal=False):
            cancelled = asyncio.create_task(cancel_me())
            sibling = asyncio.create_task(finish())
            try:
                await asyncio.wait_for(second_finished.wait(), timeout=5)
            finally:
                cancelled.cancel()
                await asyncio.gather(cancelled, return_exceptions=True)
                await sibling

        assert first.getvalue() == "first\n"
        assert second.getvalue() == "second\n"
        assert fallback.getvalue() == "restored\n"
        assert cancelled.cancelled()
