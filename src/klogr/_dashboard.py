"""A scoped dashboard for operations that update independently."""

from __future__ import annotations

from asyncio import CancelledError
from collections import Counter
from contextlib import contextmanager, nullcontext, suppress
from enum import Enum
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Group
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from klogr._progress import DashboardDisplay
from klogr.time import get_elapsed_time

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from rich.console import RenderableType

    from klogr.logger import LoggingRich


class DashboardState(str, Enum):
    """State of an operation shown in a dashboard row."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class DashboardRow(BaseModel):
    """The latest state and optional details for one operation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    state: DashboardState = DashboardState.PENDING
    attempts: int | None = Field(default=None, ge=0)
    error: str | None = None
    percent: float | None = Field(default=None, ge=0, le=100)

    def details(self) -> str:
        """Format optional fields as a single plain line."""
        parts = [self.state.value]
        if self.attempts is not None:
            parts.append(f"attempts {self.attempts}")
        if self.percent is not None:
            parts.append(f"{self.percent:g}%")
        if self.error:
            parts.append(f"last error: {_single_line(self.error)}")
        return " | ".join(parts)


def _single_line(value: str) -> str:
    return "".join(
        char if char.isprintable() or char == "\u200d" else " "
        for char in value
    )


class Dashboard:
    """Update rows by key while retaining the order in which they were added."""

    _title: str
    _present: Callable[[str], None]
    _renderer: Callable[[tuple[DashboardRow, ...]], RenderableType] | None
    _rows: dict[str, DashboardRow]
    _started: float
    _spinner: Spinner
    _lock: Lock
    _closed: bool

    def __init__(
        self,
        title: str,
        *,
        present: Callable[[str], None],
        renderer: Callable[[tuple[DashboardRow, ...]], RenderableType] | None,
    ) -> None:
        """Start a dashboard with no rows."""
        self._title = _single_line(title)
        self._present = present
        self._renderer = renderer
        self._rows = {}
        self._started = monotonic()
        self._spinner = Spinner("dots")
        self._lock = Lock()
        self._closed = False

    def update_row(self, key: str, row: DashboardRow) -> None:
        """Add or replace a row and publish its latest state if it changed."""
        with self._lock:
            if self._closed:
                message = "dashboard scope has ended"
                raise RuntimeError(message)
            if self._rows.get(key) == row:
                return
            self._rows[key] = row
        self._present(
            f"{self._title} | {_single_line(row.name)}: {row.details()}"
        )

    def __rich__(self) -> Group:
        """Render the elapsed timer and current rows in one display."""
        with self._lock:
            rows = tuple(self._rows.values())
        now = monotonic()
        heading = Text(
            f"{self._title} | elapsed {get_elapsed_time(now - self._started)}"
        )
        banner: RenderableType = heading
        if any(row.state is DashboardState.RUNNING for row in rows):
            self._spinner.update(text=heading)
            banner = self._spinner.render(now)
        if self._renderer is not None:
            return Group(banner, self._renderer(rows))
        table = Table(expand=True)
        table.add_column("Operation", ratio=1, overflow="fold")
        table.add_column("Status", ratio=2, overflow="fold")
        for row in rows:
            table.add_row(Text(_single_line(row.name)), Text(row.details()))
        return Group(banner, table)

    def finish(self, outcome: str) -> str:
        """Close updates to the scope and return a plain-text summary."""
        with self._lock:
            self._closed = True
            counts = Counter(row.state for row in self._rows.values())
        summary = ", ".join(
            f"{counts[state]} {state.value}"
            for state in DashboardState
            if counts[state]
        )
        elapsed = get_elapsed_time(monotonic() - self._started)
        return f"{self._title}: {outcome} | {summary or 'no operations'} | elapsed {elapsed}"


@contextmanager
def dashboard_scope(
    logger: LoggingRich,
    title: str,
    *,
    render: Callable[[tuple[DashboardRow, ...]], RenderableType] | None,
) -> Iterator[Dashboard]:
    """Share a dashboard display or write row changes to text destinations."""
    terminal = logger.console
    display = logger._dashboard_for(terminal)
    owns_display = display is None
    if (
        display is None
        and terminal.is_terminal
        and terminal.is_interactive
        and terminal in logger._message_consoles
    ):
        display = DashboardDisplay(terminal, transient=True)

    def publish(message: str) -> None:
        for console in logger._message_consoles:
            if display is None or console is not terminal:
                console.print(message, markup=False, highlight=False)
        if display is not None:
            display.refresh()

    dashboard = Dashboard(title, present=publish, renderer=render)

    def finish(outcome: str) -> None:
        summary = dashboard.finish(outcome)
        try:
            if display is not None:
                display.remove_status(dashboard)
        finally:
            if owns_display and display is not None:
                display.close()
        for console in logger._message_consoles:
            console.print(summary, markup=False, highlight=False)

    scope = (
        logger._bind_dashboard(display)
        if display is not None
        else nullcontext()
    )
    with scope:
        try:
            if display is not None:
                display.add_status(dashboard)
            yield dashboard
        except BaseException as error:
            outcome = (
                "cancelled"
                if isinstance(error, (CancelledError, KeyboardInterrupt))
                else "failed"
            )
            with suppress(Exception):
                finish(outcome)
            raise
        else:
            finish("finished")
