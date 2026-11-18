"""Build the Rich progress display used by the logger."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich import progress
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console


class IterationsPerSecondColumn(progress.ProgressColumn):
    """Display the current or final iteration rate."""

    def render(self, task: progress.Task) -> Text:
        """Render the iterations per second column."""
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("? it/s", style="progress.data.speed")
        return Text(f"{speed:.2f} it/s", style="progress.data.speed")


def make_progress(*, console: Console, **kwargs: Any) -> progress.Progress:
    """Build a progress display with the shared columns."""
    kwargs.setdefault("refresh_per_second", 1)
    return progress.Progress(
        "[progress.description]{task.description}",
        progress.BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        progress.MofNCompleteColumn(),
        progress.TimeRemainingColumn(),
        progress.TimeElapsedColumn(),
        IterationsPerSecondColumn(),
        console=console,
        **kwargs,
    )
