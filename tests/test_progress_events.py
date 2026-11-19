"""Exercise structured progress and dashboard output."""

import asyncio
import json
import sys
from io import StringIO
from unittest import IsolatedAsyncioTestCase, TestCase

from pydantic import ValidationError
from rich.console import Console
from rich.text import Text

from klogr import (
    DashboardRow,
    DashboardState,
    LoggingRich,
    ProgressEvent,
    ProgressStatus,
)


class LiveDashboardTests(TestCase):
    """Check table updates and cleanup through the public dashboard API."""

    def test_rows_statuses_progress_and_messages_share_the_terminal(
        self,
    ) -> None:
        """Render Text statuses and update rows without another Live display."""
        terminal, persistent = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal,
                force_terminal=True,
                force_interactive=True,
                width=52,
            )
        )
        with (
            logger.route(persistent),
            logger.live_dashboard("Search") as dashboard,
            logger.status(Text("Checking", style="cyan")) as status,
            logger.progress() as progress,
        ):
            status.update(Text("Retrying", style="red"))
            progress.add_task("Decode", total=1, completed=1)
            dashboard.update_row(
                "east",
                DashboardRow(
                    name="[red]東京",
                    state=DashboardState.RUNNING,
                    percent=75,
                ),
            )
            logger.print("ordinary message", force=True)
            dashboard.update_row(
                "east",
                DashboardRow(name="[red]東京", state=DashboardState.SUCCEEDED),
            )
        displayed = terminal.getvalue()
        assert "[red]東京" in displayed
        assert "Retrying" in displayed
        assert "Decode" in displayed
        written = persistent.getvalue()
        assert "ordinary message" in written
        assert "1 succeeded" in written
        assert "\x1b" not in written

    def test_redirected_dashboard_records_changes_and_failure(self) -> None:
        """Keep literal error text and show a failure summary once."""
        output = StringIO()
        logger = LoggingRich()
        row = DashboardRow(
            name="east",
            state=DashboardState.FAILED,
            attempts=2,
            error="[bad]\nretry",
        )
        try:
            with (
                logger.route(output, terminal=False),
                logger.live_dashboard("Search") as dashboard,
            ):
                dashboard.update_row("east", row)
                dashboard.update_row("east", row)
                message = "search failed"
                raise RuntimeError(message)
        except RuntimeError as exc:
            received = str(exc)
        else:
            self.fail("The dashboard swallowed the error")
        assert received == "search failed"
        assert output.getvalue().count("last error: [bad] retry") == 1
        assert "Search: failed | 1 failed" in output.getvalue()

    def test_native_status_accepts_strings_and_text(self) -> None:
        """Keep the native spinner API for either message type."""
        output = StringIO()
        logger = LoggingRich(
            console=Console(
                file=output, force_terminal=True, force_interactive=True
            )
        )
        with logger.status("Waiting") as status:
            status.update(Text("Still waiting"))
        with logger.status(Text("Done", style="cyan")) as status:
            logger.print(status.renderable, force=True)
        assert "Done" in output.getvalue()


class ConcurrentDashboardTests(IsolatedAsyncioTestCase):
    """Verify concurrent updates and cancellation on one event loop."""

    async def test_cancelled_dashboard_reports_both_task_updates(self) -> None:
        """Keep completed row updates and stop the live display on cancellation."""
        terminal = StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal, force_terminal=True, force_interactive=True
            )
        )
        reached = asyncio.Event()

        async def run() -> None:
            with logger.live_dashboard("Search") as dashboard:

                async def complete(region: str) -> None:
                    dashboard.update_row(
                        region,
                        DashboardRow(
                            name=region, state=DashboardState.SUCCEEDED
                        ),
                    )

                await asyncio.gather(complete("east"), complete("west"))
                reached.set()
                await asyncio.Future[None]()

        task = asyncio.create_task(run())
        await asyncio.wait_for(reached.wait(), timeout=2)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()
        assert "Search: cancelled | 2 succeeded" in terminal.getvalue()
        with logger.live_dashboard("Next search"):
            pass
        assert "Next search: finished" in terminal.getvalue()


class ProgressEventTests(TestCase):
    """Verify stage and frame updates through public routes."""

    def test_dashboard_shares_live_display_with_both_progress_apis(
        self,
    ) -> None:
        """Start a manual bar first and track an iterable alongside it."""
        terminal, text, events = StringIO(), StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal,
                force_terminal=True,
                force_interactive=True,
                width=100,
            )
        )
        stdout, stderr = sys.stdout, sys.stderr
        with (
            logger.route(text),
            logger.progress_events(
                dashboard=lambda event: f"Stage {event.stage}", jsonl=events
            ) as publish,
            logger.progress() as progress,
        ):
            task = progress.add_task("Manual task", total=2)
            publish(
                ProgressEvent(
                    stage="decode",
                    status=ProgressStatus.RUNNING,
                    elapsed_seconds=1,
                )
            )
            logger.print("diagnostic")
            for item in logger.track(range(2), description="Tracked items"):
                progress.update(task, completed=item + 1, refresh=True)
            assert sys.stdout is stdout
            assert sys.stderr is stderr
        output = terminal.getvalue()
        assert "Stage decode" in output
        assert "Manual task" in output
        assert "Tracked items" in output
        assert "diagnostic" in output
        assert text.getvalue() == "decode: running (1.00s)\ndiagnostic\n"
        assert json.loads(events.getvalue())["stage"] == "decode"

    def test_completed_frames_cannot_exceed_the_total(self) -> None:
        """Reject impossible frame counts before reporting."""
        try:
            ProgressEvent(
                stage="frames",
                status=ProgressStatus.RUNNING,
                elapsed_seconds=1,
                completed=8,
                total=5,
            )
        except ValidationError:
            return
        self.fail("Invalid frame counts were accepted")

    def test_json_lines_sink_cannot_also_receive_human_output(self) -> None:
        """Fail before writing when a single stream has conflicting formats."""
        output = StringIO()
        logger = LoggingRich()
        event = ProgressEvent(
            stage="frames", status=ProgressStatus.STARTED, elapsed_seconds=0
        )
        try:
            with (
                logger.route(output, terminal=False),
                logger.progress_events(jsonl=output) as publish,
            ):
                publish(event)
        except ValueError:
            pass
        else:
            self.fail("Mixed output formats should be rejected")
        assert output.getvalue() == ""

    def test_file_route_throttles_running_updates_and_keeps_final_states(
        self,
    ) -> None:
        """Write each JSON event and keep terminal statuses in the text log."""
        text_file, jsonl = StringIO(), StringIO()
        logger = LoggingRich()
        events = [
            ProgressEvent(
                stage="generate",
                status=ProgressStatus.STARTED,
                elapsed_seconds=0,
            ),
            ProgressEvent(
                stage="frames",
                status=ProgressStatus.RUNNING,
                elapsed_seconds=1,
                completed=1,
                total=5,
            ),
            ProgressEvent(
                stage="frames",
                status=ProgressStatus.RUNNING,
                elapsed_seconds=2,
                completed=2,
                total=5,
            ),
            ProgressEvent(
                stage="frames",
                status=ProgressStatus.COMPLETED,
                elapsed_seconds=3,
                completed=5,
                total=5,
            ),
            ProgressEvent(
                stage="generate",
                status=ProgressStatus.FAILED,
                elapsed_seconds=4,
            ),
        ]
        with (
            logger.route(text_file, terminal=False),
            logger.progress_events(jsonl=jsonl, interval=3600) as publish,
        ):
            for event in events:
                publish(event)

        records = [json.loads(line) for line in jsonl.getvalue().splitlines()]
        assert records == [event.model_dump(mode="json") for event in events]
        output = text_file.getvalue()
        assert "generate: started" in output
        assert "1/5" in output
        assert "2/5" not in output
        assert "frames: completed" in output
        assert "generate: failed" in output
        assert not jsonl.closed

    def test_interactive_dashboard_does_not_write_redraws_to_file(
        self,
    ) -> None:
        """Render custom dashboard content exclusively on the terminal."""
        terminal, text_file = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal, force_terminal=True, force_interactive=True
            )
        )
        stdout, stderr = sys.stdout, sys.stderr
        with (
            logger.route(text_file),
            logger.progress_events(
                dashboard=lambda event: f"Dashboard for {event.stage}"
            ) as publish,
        ):
            publish(
                ProgressEvent(
                    stage="frames",
                    status=ProgressStatus.COMPLETED,
                    elapsed_seconds=1,
                )
            )
            assert sys.stdout is stdout
            assert sys.stderr is stderr
        assert "Dashboard for frames" in terminal.getvalue()
        assert text_file.getvalue() == "frames: completed (1.00s)\n"

    def test_noninteractive_console_gets_plain_progress(self) -> None:
        """Fall back to a progress line for redirected console output."""
        terminal = StringIO()
        logger = LoggingRich(console=Console(file=terminal))
        with logger.progress_events(
            dashboard=lambda event: f"Dashboard for {event.stage}"
        ) as publish:
            publish(
                ProgressEvent(
                    stage="frames",
                    status=ProgressStatus.COMPLETED,
                    elapsed_seconds=1,
                )
            )
        assert terminal.getvalue() == "frames: completed (1.00s)\n"
