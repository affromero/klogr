"""Render a live dashboard and persist the same events in two formats."""

from argparse import ArgumentParser
from pathlib import Path
from time import monotonic, sleep

from rich.table import Table

from klogr import FileMode, ProgressEvent, ProgressStatus, get_logger


def run(output: Path) -> None:
    """Show two processing stages and write text and JSON Lines logs."""
    output.mkdir(parents=True, exist_ok=True)
    logger = get_logger(stderr=True)
    latest: dict[str, ProgressEvent] = {}

    def dashboard(event: ProgressEvent) -> Table:
        """Render the latest event for each stage."""
        latest[event.stage] = event
        table = Table(title="Frame processing")
        table.add_column("Stage", style="cyan")
        table.add_column("Status")
        table.add_column("Frames", justify="right")
        table.add_column("Elapsed", justify="right")
        for update in latest.values():
            table.add_row(
                update.stage,
                update.status.value,
                f"{update.completed}/{update.total}",
                f"{update.elapsed_seconds:.2f}s",
            )
        return table

    text_path = output / "run.log"
    events_path = output / "events.jsonl"
    with (
        logger.route_file(text_path, mode=FileMode.OVERWRITE),
        events_path.open("w", encoding="utf-8") as events,
        logger.progress_events(
            dashboard=dashboard, jsonl=events, interval=0.5
        ) as publish,
    ):
        for stage, total in (("Decode", 8), ("Score", 10)):
            started = monotonic()
            publish(
                ProgressEvent(
                    stage=stage,
                    status=ProgressStatus.STARTED,
                    elapsed_seconds=0,
                    completed=0,
                    total=total,
                )
            )
            for completed in range(1, total + 1):
                sleep(0.10)
                status = (
                    ProgressStatus.COMPLETED
                    if completed == total
                    else ProgressStatus.RUNNING
                )
                publish(
                    ProgressEvent(
                        stage=stage,
                        status=status,
                        elapsed_seconds=monotonic() - started,
                        completed=completed,
                        total=total,
                    )
                )
    logger.print(f"Text log: {text_path}")
    logger.print(f"Event stream: {events_path}")


def main() -> None:
    """Read the output directory and run the dashboard demo."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)


if __name__ == "__main__":
    main()
