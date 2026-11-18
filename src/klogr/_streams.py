"""Mirror Python's standard streams to plain text log files."""

from __future__ import annotations

import re
import sys
from io import TextIOBase
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from rich.console import Console

if TYPE_CHECKING:
    from typing import IO, TextIO

_ANSI_ESCAPE = re.compile(
    r"\x1B(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])"
)


class StdoutDuplicator:
    """Duplicate a standard stream to a file, stripping ANSI codes."""

    original_stdout: TextIO
    file_handle: TextIO

    def __init__(self, original_stdout: TextIO, file_path: str | Path) -> None:
        """Open the log file and keep the original standard stream."""
        self.original_stdout = original_stdout
        self.file_handle = Path(file_path).open("w", encoding="utf-8")

    def write(self, data: str) -> int:
        """Write to the original stream and strip ANSI codes from the file."""
        result = self.original_stdout.write(data)
        self.file_handle.write(_ANSI_ESCAPE.sub("", data))
        self.file_handle.flush()
        return result

    def flush(self) -> None:
        """Flush the original stream and file."""
        self.original_stdout.flush()
        self.file_handle.flush()

    def close(self) -> None:
        """Close the log file."""
        self.file_handle.close()

    def __getattr__(self, name: str) -> Any:
        """Delegate other attributes to the original stream."""
        return getattr(self.original_stdout, name)


class StreamMirror:
    """Own the active stream duplicator and the console it replaced."""

    original_console: Console
    stream_name: str
    console: Console
    duplicator: StdoutDuplicator

    def __init__(
        self,
        console: Console,
        file_path: str | Path,
        *,
        previous: StreamMirror | None,
        console_options: dict[str, Any],
    ) -> None:
        """Install the new mirror after its console and log file are ready."""
        self.original_console = (
            previous.original_console if previous is not None else console
        )
        stderr = self.original_console.stderr
        self.stream_name = "stderr" if stderr else "stdout"
        original = (
            previous.duplicator.original_stdout
            if previous is not None
            else getattr(sys, self.stream_name)
        )
        options = console_options.copy()
        options.update(stderr=stderr, force_terminal=True)
        self.console = Console(**options)
        self.duplicator = StdoutDuplicator(original, file_path)
        if previous is not None:
            previous.close()
        setattr(sys, self.stream_name, self.duplicator)

    def close(self) -> None:
        """Restore the original stream and close the log file."""
        setattr(sys, self.stream_name, self.duplicator.original_stdout)
        self.duplicator.close()


class _PlainWriter(TextIOBase):
    stream: TextIO

    def __init__(self, stream: TextIO) -> None:
        super().__init__()
        self.stream = stream

    def write(self, data: str) -> int:
        """Remove any embedded terminal sequences from the rendered text."""
        self.stream.write(_ANSI_ESCAPE.sub("", data))
        return len(data)

    def flush(self) -> None:
        """Flush the destination without taking ownership."""
        self.stream.flush()

    def close(self) -> None:
        """Leave the caller-owned stream open."""


class MessageRoute:
    """Hold a console for each distinct destination in a logging scope."""

    terminal: Console | None
    files: tuple[tuple[TextIO, Console], ...]

    def __init__(
        self, source: Console, streams: tuple[TextIO, ...], *, terminal: bool
    ) -> None:
        """Keep the selected terminal and deduplicate explicit streams."""
        self.terminal = source if terminal else None
        self.files = tuple(
            (stream, _plain_console(source, stream))
            for stream in {id(stream): stream for stream in streams}.values()
        )

    def consoles(self) -> tuple[Console, ...]:
        """Select distinct destinations using the current terminal stream."""
        terminal = self.terminal
        if terminal is None:
            return tuple(console for _, console in self.files)
        terminal_file = terminal.file
        return (
            terminal,
            *(
                console
                for stream, console in self.files
                if stream is not terminal_file
            ),
        )


def _plain_console(source: Console, stream: TextIO) -> Console:
    # Rich only writes and flushes this stream, both provided by TextIOBase.
    writer = cast("IO[str]", _PlainWriter(stream))
    console = Console(
        file=writer,
        color_system=None,
        force_terminal=False,
        force_jupyter=False,
        width=source.width,
        soft_wrap=source.soft_wrap,
        tab_size=source.tab_size,
        style=source.style,
        quiet=source.quiet,
        markup=source._markup,
        emoji=source._emoji,
        emoji_variant=source._emoji_variant,
        highlight=source._highlight,
        highlighter=source.highlighter,
        log_time=source._log_render.show_time,
        log_path=source._log_render.show_path,
        log_time_format=source._log_render.time_format,
        get_datetime=source.get_datetime,
    )
    console._log_render.omit_repeated_times = (
        source._log_render.omit_repeated_times
    )
    return console
