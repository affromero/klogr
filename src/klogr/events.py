"""Structured progress reporting for terminal, text, and JSON Lines sinks."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from enum import Enum
from math import isfinite
from time import monotonic
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, model_validator
from rich.live import Live

from klogr._streams import console_stream

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import TextIO

    from rich.console import Console, RenderableType


class ProgressStatus(str, Enum):
    """The state of a reported stage."""

    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressEvent(BaseModel):
    """A stage update with elapsed seconds and optional work counts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str = Field(min_length=1)
    status: ProgressStatus
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> ProgressEvent:
        """Keep completed work within a known total."""
        if (
            self.completed is not None
            and self.total is not None
            and self.completed > self.total
        ):
            message = "completed work exceeds total work"
            raise ValueError(message)
        return self

    def text(self) -> str:
        """Render a single human-readable progress line."""
        line = (
            f"{self.stage}: {self.status.value} ({self.elapsed_seconds:.2f}s)"
        )
        if self.completed is not None:
            count = str(self.completed)
            if self.total is not None:
                count = f"{count}/{self.total}"
            return f"{line} {count}"
        return line


@contextmanager
def report_progress(
    *,
    destinations: Callable[[], tuple[Console, ...]],
    terminal: Console,
    dashboard: Callable[[ProgressEvent], RenderableType] | None,
    jsonl: TextIO | None,
    interval: float,
) -> Iterator[Callable[[ProgressEvent], None]]:
    """Yield a reporter with optional live rendering and text throttling."""
    if not isfinite(interval) or interval < 0:
        message = "progress interval must be finite and nonnegative"
        raise ValueError(message)
    live = None
    last_text: dict[str, tuple[ProgressStatus, float]] = {}

    with ExitStack() as scope:

        def publish(event: ProgressEvent) -> None:
            nonlocal live
            consoles = destinations()
            interactive = (
                dashboard is not None
                and terminal.is_terminal
                and terminal.is_interactive
                and any(console is terminal for console in consoles)
            )
            if jsonl is not None:
                if any(
                    console_stream(console) is jsonl for console in consoles
                ):
                    message = "JSON Lines requires a separate output stream"
                    raise ValueError(message)
                jsonl.write(event.model_dump_json() + "\n")
                jsonl.flush()
            if interactive and dashboard is not None:
                renderable = dashboard(event)
                if live is None:
                    live = scope.enter_context(
                        Live(
                            renderable,
                            console=terminal,
                            auto_refresh=False,
                            redirect_stdout=False,
                            redirect_stderr=False,
                        )
                    )
                else:
                    live.update(renderable, refresh=True)

            now = monotonic()
            previous = last_text.get(event.stage)
            if (
                event.status is ProgressStatus.RUNNING
                and previous is not None
                and previous[0] is event.status
                and now - previous[1] < interval
            ):
                return
            last_text[event.stage] = (event.status, now)
            for console in consoles:
                if not (interactive and console is terminal):
                    console.print(event.text(), markup=False, highlight=False)

        yield publish
