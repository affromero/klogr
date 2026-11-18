"""Render an indeterminate status with a monotonic elapsed clock."""

from __future__ import annotations

from asyncio import CancelledError
from contextlib import contextmanager, suppress
from math import isfinite
from typing import TYPE_CHECKING, Protocol

from rich.spinner import Spinner
from rich.text import Text

from klogr.time import get_elapsed_time

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from rich.console import Console, ConsoleOptions, RenderResult


class _StatusWriter(Protocol):
    def __call__(self, message: str, *, persistent: bool) -> None: ...


class TimedStatus:
    """Update the caller's latest status without resetting elapsed time."""

    _label: str
    _clock: Callable[[], float]
    _write: _StatusWriter
    _interval: float | None
    _started: float
    _last_write: float
    _message: str
    _spinner: Spinner

    def __init__(
        self,
        label: str,
        *,
        clock: Callable[[], float],
        write: _StatusWriter,
        interval: float | None,
    ) -> None:
        """Set up the status with an optional text update interval."""
        if interval is not None and (not isfinite(interval) or interval < 0):
            message = "status interval must be finite and nonnegative"
            raise ValueError(message)
        self._label = label
        self._clock = clock
        self._write = write
        self._interval = interval
        self._started = clock()
        self._last_write = self._started
        self._message = ""
        self._spinner = Spinner("dots")

    @property
    def elapsed(self) -> float:
        """Return elapsed monotonic seconds since the scope began."""
        return self._clock() - self._started

    def _line(self, message: str) -> str:
        elapsed = get_elapsed_time(self.elapsed)
        return f"{self._label}: {message} (elapsed {elapsed})"

    def update(
        self,
        message: str,
        *,
        label: str | None = None,
        percent: float | None = None,
        service_eta: str | None = None,
    ) -> None:
        """Set status text and optional percentage or service-provided ETA."""
        if percent is not None:
            if not 0 <= percent <= 100:
                error = "status percentage must be between 0 and 100"
                raise ValueError(error)
            message = f"{message} ({percent:g}%)"
        if service_eta is not None:
            message = f"{message} | service ETA {service_eta}"
        if label is not None:
            self._label = label
        self._message = message
        now = self._clock()
        if (
            self._interval is not None
            and now - self._last_write >= self._interval
        ):
            self._last_write = now
            self._write(self._line(message), persistent=False)

    def report(self, outcome: str) -> None:
        """Write an entry or outcome to the configured text destinations."""
        self._write(self._line(outcome), persistent=True)

    @contextmanager
    def outcomes(
        self, *, entry: bool, completion: bool
    ) -> Iterator[TimedStatus]:
        """Report the scope's outcome and preserve exceptions from its body."""
        if entry:
            self.report("started")
        try:
            yield self
        except BaseException as exc:
            if completion:
                outcome = (
                    "cancelled"
                    if isinstance(exc, (CancelledError, KeyboardInterrupt))
                    else "failed"
                )
                with suppress(Exception):
                    self.report(outcome)
            raise
        else:
            if completion:
                self.report("completed")

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render the latest status and elapsed time on every live refresh."""
        self._spinner.update(text=Text(self._line(self._message or "waiting")))
        yield self._spinner.render(self._clock())
