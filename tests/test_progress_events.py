"""Exercise structured progress and dashboard output."""

import json
import sys
from io import StringIO
from unittest import TestCase

from pydantic import ValidationError
from rich.console import Console

from klogr import LoggingRich, ProgressEvent, ProgressStatus


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
