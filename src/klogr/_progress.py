"""Build the Rich progress display used by the logger."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rich import progress
from rich.console import Group
from rich.live import Live
from rich.progress import Progress as _RichProgress
from rich.text import Text

if TYPE_CHECKING:
    from rich.console import Console, RenderableType

Progress = _RichProgress


class IterationsPerSecondColumn(progress.ProgressColumn):
    """Display the current or final iteration rate."""

    def render(self, task: progress.Task) -> Text:
        """Render the iterations per second column."""
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("? it/s", style="progress.data.speed")
        return Text(f"{speed:.2f} it/s", style="progress.data.speed")


class DashboardDisplay:
    """Own one live display for the dashboard and its progress bars."""

    console: Console
    live: Live
    active: bool
    _dashboard: RenderableType | None
    _bars: tuple[Progress, ...]
    _statuses: tuple[RenderableType, ...]

    def __init__(self, console: Console, *, transient: bool = False) -> None:
        """Prepare the display without writing until content becomes available."""
        self.console = console
        self.active = True
        self._dashboard = None
        self._bars = ()
        self._statuses = ()
        self.live = Live(
            console=console,
            get_renderable=self.render,
            redirect_stdout=False,
            redirect_stderr=False,
            transient=transient,
        )

    def render(self) -> Group:
        """Render the dashboard and every attached progress bar."""
        return (
            Group(self._dashboard, *self._bars, *self._statuses)
            if self._dashboard is not None
            else Group(*self._bars, *self._statuses)
        )

    def add_status(self, status: RenderableType) -> None:
        """Show a timed status alongside other live content."""
        self._statuses = (*self._statuses, status)
        self.refresh()

    def remove_status(self, status: RenderableType) -> None:
        """Remove the status from the live display."""
        self._statuses = tuple(
            item for item in self._statuses if item is not status
        )
        self.refresh()

    @property
    def has_statuses(self) -> bool:
        """Return whether the display still owns any timed statuses."""
        return bool(self._statuses)

    @property
    def interactive(self) -> bool:
        """Check whether the dashboard can render to its current terminal."""
        return (
            self.active
            and self.console.is_terminal
            and self.console.is_interactive
        )

    def update(self, renderable: RenderableType) -> None:
        """Set the latest dashboard content."""
        self._dashboard = renderable
        self.refresh()

    def attach(self, bar: Progress) -> None:
        """Add a progress bar to the shared display."""
        if self.active and bar not in self._bars:
            self._bars = (*self._bars, bar)
            self.refresh()

    def detach(self, bar: Progress) -> None:
        """Remove a progress bar and retain its final row when requested."""
        if bar not in self._bars:
            return
        self._bars = tuple(item for item in self._bars if item is not bar)
        if self.active:
            if not bar.live.transient:
                self.console.print(bar)
            self.refresh()

    def refresh(self) -> None:
        """Start or refresh the shared live display."""
        if self.active:
            if self.live.is_started:
                self.live.refresh()
            else:
                self.live.start(refresh=True)

    def close(self) -> None:
        """Finish the dashboard and release the shared live display."""
        self.active = False
        try:
            self.live.stop()
        finally:
            self._bars = ()
            self._statuses = ()


class DashboardProgress(Progress):
    """Render Rich progress inside a dashboard's live display."""

    _display: DashboardDisplay
    _standalone: bool
    _attached: bool

    def __init__(
        self,
        *columns: str | progress.ProgressColumn,
        display: DashboardDisplay,
        **kwargs: Any,
    ) -> None:
        """Create a progress bar that can attach to the shared display."""
        super().__init__(*columns, **kwargs)
        self._display = display
        self._standalone = False
        self._attached = False

    def start(self) -> None:
        """Attach without starting a second live display."""
        if not self.disable:
            self._standalone = not self._display.interactive
            if self._standalone:
                super().start()
            else:
                self._attached = True
                self._display.attach(self)

    def stop(self) -> None:
        """Detach without stopping the dashboard."""
        if self._standalone:
            super().stop()
        else:
            self._attached = False
            self._display.detach(self)

    def refresh(self) -> None:
        """Refresh the live display after an explicit progress update."""
        if self._standalone:
            super().refresh()
        elif self._attached and not self.disable:
            self._display.refresh()


def make_progress(
    *, console: Console, display: DashboardDisplay | None = None, **kwargs: Any
) -> Progress:
    """Build a progress display with the shared columns."""
    kwargs.setdefault("refresh_per_second", 1)
    columns = (
        "[progress.description]{task.description}",
        progress.BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        progress.MofNCompleteColumn(),
        progress.TimeRemainingColumn(),
        progress.TimeElapsedColumn(),
        IterationsPerSecondColumn(),
    )
    if display is None:
        return Progress(*columns, console=console, **kwargs)
    return DashboardProgress(
        *columns, console=console, display=display, **kwargs
    )
