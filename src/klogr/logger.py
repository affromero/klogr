"""Rich-based logger: :class:`LoggingRich`, :class:`LoggingTable`, :func:`get_logger`."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Sized
from contextvars import ContextVar
from dataclasses import field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import dotenv
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass
from rich.box import ROUNDED, Box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from klogr._progress import (
    IterationsPerSecondColumn as _IterationsPerSecondColumn,
)
from klogr._progress import make_progress
from klogr._streams import StdoutDuplicator as _StdoutDuplicator
from klogr._streams import StreamMirror, routed_consoles

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator
    from typing import TextIO, TypeVar

    from rich.progress import Progress

    _T = TypeVar("_T")

SECRET_PLACEHOLDERS = {"INFISICAL", "AWS-SECRET"}
IterationsPerSecondColumn = _IterationsPerSecondColumn
StdoutDuplicator = _StdoutDuplicator


def _load_non_secret_dotenv() -> None:
    """Load logging config while leaving credential placeholders untouched."""
    dotenv_file = dotenv.find_dotenv(usecwd=True)
    if not dotenv_file:
        return
    for key, raw_value in dotenv.dotenv_values(dotenv_file).items():
        if raw_value is None:
            continue
        if raw_value.strip().upper() in SECRET_PLACEHOLDERS:
            continue
        os.environ.setdefault(key, raw_value)


_load_non_secret_dotenv()
DISABLE_LOGGING = os.getenv("DISABLE_LOGGING", "False") == "True"
LOG_DEBUG = os.getenv("LOG_DEBUG", "False") == "True"
LOG_WARNING = os.getenv("LOG_WARNING", "True") == "True"
JSON_FORMATTER = os.getenv("JSON_FORMATTER", "False") == "True"
RICH_OMIT_REPEATED_TIMES = (
    os.getenv("RICH_OMIT_REPEATED_TIMES", "False") == "True"
)

DEFAULT_VERBOSITY = {
    "info": not DISABLE_LOGGING,
    "debug": LOG_DEBUG and not DISABLE_LOGGING,
    "warning": LOG_WARNING and not DISABLE_LOGGING,
    "error": not DISABLE_LOGGING,
    "success": not DISABLE_LOGGING,
    "rule": not DISABLE_LOGGING,
    "log": not DISABLE_LOGGING,
    "print": not DISABLE_LOGGING,
    "save_image": not DISABLE_LOGGING,
    "make_image_grid": not DISABLE_LOGGING,
}


def override_from_dotenv(
    env_var_name: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Override decorator that overrides self.verbosity with the value from the specified environment variable.

    This decorator checks if the specified environment variable exists and has a non-empty value.
    If it does, it attempts to parse the value as JSON and replace self.verbosity with the parsed dictionary.
    If the environment variable is not found or parsing fails, it falls back to the original method behavior.

    Args:
        env_var_name: The name of the environment variable to check for verbosity configuration.

    Returns:
        The decorated function with potentially overridden verbosity.

    Example:
        >>> @override_from_dotenv("LOG_DEBUG")
        >>> def debug(self, msg: str, **kwargs: Any) -> None:
        ...     # self.verbosity will be overridden if LOG_DEBUG env var is set
        ...     pass

    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapper(self: LoggingRich, *args: Any, **kwargs: Any) -> Any:
            # Check if the environment variable exists and has a value
            env_value = os.getenv(env_var_name)
            if env_value is None:
                dotenv_file = dotenv.find_dotenv(usecwd=True)
                if dotenv_file:
                    env_value = dotenv.dotenv_values(dotenv_file).get(
                        env_var_name
                    )
            if env_value and env_value.strip():
                name = env_var_name.split("_")[1].lower()
                if name not in self.verbosity:
                    msg = f"{name=} not in {self.verbosity=}"
                    raise ValueError(msg)
                self.verbosity[name] = env_value.lower() == "true"

            # Call the original function
            return func(self, *args, **kwargs)

        return wrapper

    return decorator


class LoggingTable:
    """LoggingTable class."""

    columns: list[str]
    """Columns of the table."""
    colors: list[str]
    """Colors of the table. Same length as columns."""
    rows: list[list[str]]
    """Rows of the table. Same length as columns."""
    title: str
    """Title of the table."""
    box: Box = ROUNDED
    """Box style of the table. Default is ROUNDED."""


@dataclass(config=ConfigDict(arbitrary_types_allowed=True, extra="forbid"))
class LoggingRich:
    """LoggingRich class."""

    # https://rich.readthedocs.io/en/stable/appendix/colors.html#appendix-colors
    modes: dict[str, str] = field(
        default_factory=lambda: {
            "info": "[white][[INFO]] {}[/white]",
            "debug": "[blue][[:hedgehog:DEBUG]] {}[/blue]",
            "warning": "[italic yellow][[:warning: WARNING]] {}[/italic yellow]",
            "error": "[bold red][[:x:ERROR]] {}[/bold red]",
            "success": "[bold green][[:white_check_mark:SUCCESS]] {}[/bold green]",
            "log": "{}",
        },
    )
    """ Modes for logging. """

    stack_offset: int = 2
    """ Offset for the stack trace. """

    console: Console = field(default_factory=Console)
    """ Rich console. """

    verbosity: dict[str, bool] = field(
        default_factory=lambda: DEFAULT_VERBOSITY,
    )
    """ Verbosity levels. """

    id: str = ""
    """ ID for the logger. """

    stdout_duplicator: _StdoutDuplicator | None = None
    """ Standard stream duplicator for file output when enabled. """

    _stream_mirror: StreamMirror | None = field(
        default=None, init=False, repr=False
    )

    _route: ContextVar[tuple[Console, ...] | None] = field(
        default_factory=lambda: ContextVar("klogr_route", default=None),
        init=False,
        repr=False,
    )

    _logged_once: set[str] = field(default_factory=set)
    """ Set of messages that have been logged once. """

    def __post_init__(self) -> None:
        """Disable the omission of repeated times in console's log render."""
        self.console._log_render.omit_repeated_times = RICH_OMIT_REPEATED_TIMES
        # default is True, i.e. omit timestamp if it's the same as last log line
        # https://github.com/Textualize/rich/issues/459

    def __hash__(self) -> int:
        """Hash the logger."""
        return hash((self.id, frozenset(self.verbosity.items())))

    def __eq__(self, other: object) -> bool:
        """Check if the logger is equal to another object."""
        return (
            isinstance(other, LoggingRich)
            and self.id == other.id
            and self.verbosity == other.verbosity
        )

    def set_id(self, _id: str, /) -> None:
        """Set the ID for the logger."""
        self.id = _id

    def get_modes(self) -> dict[str, str]:
        """Get the modes for the logger."""
        modes = self.modes.copy()
        if self.id:
            modes["log"] = (
                f"[uu slate_blue1]ID:{self.id}[/uu slate_blue1] "
                + modes["log"]
            )
        return modes

    def is_file_enabled(self) -> bool:
        """Check if the logging file is enabled."""
        stream = self.console.file
        return self.stdout_duplicator is not None or (
            stream is not sys.stdout and stream is not sys.stderr
        )

    def track(
        self,
        iterable: Iterable[_T],
        /,
        *,
        description: str,
        total: int | None = None,
        transient: bool = False,
        **kwargs: Any,
    ) -> Iterable[_T]:
        """Track an iterable with a progress bar showing elapsed and remaining time.

        Args:
            iterable: The iterable to track.
            description: Description shown next to the progress bar.
            total: Total number of items. If None, attempts to get len(iterable).
            transient: If True, the progress bar disappears after completion.
            **kwargs: Additional keyword arguments passed to Progress.

        Yields:
            Items from the iterable.

        """
        if total is None and isinstance(iterable, Sized):
            total = len(iterable)

        console = kwargs.pop("console", self.console)
        with make_progress(
            console=console,
            transient=transient,
            **kwargs,
        ) as prog:
            task_id = prog.add_task(description, total=total)
            for item in iterable:
                yield item
                prog.update(task_id, advance=1)

    def progress(self) -> Progress:
        """Create and return a Rich Progress context manager with a custom progress bar.

        Returns:
            progress.Progress: A Rich Progress context manager configured with
                description, bar, percentage, time remaining, and time elapsed columns.

        Example:
            with logger.progress() as prog:
                task = prog.add_task("Processing", total=100)
                for i in range(100):
                    # do work
                    prog.update(task, advance=1)

        """
        return make_progress(console=self.console)

    def panel(
        self,
        msg: list[str],
        *,
        title: str,
        subtitle: str | None = None,
        border_style: str = "none",
        style: str = "none",
    ) -> None:
        """Print a panel with a title and border style."""
        self.print(
            Panel(
                "\n".join(msg),
                title=title,
                subtitle=subtitle,
                border_style=border_style,
                style=style,
            )
        )

    def table(self, table: LoggingTable) -> None:
        """Print a table with a title and border style."""
        logging_table = Table(title=table.title, box=table.box)

        for column, color in zip(table.columns, table.colors, strict=False):
            logging_table.add_column(column, style=color)

        for row in table.rows:
            logging_table.add_row(*row)

        self.print(logging_table)

    def success_once(
        self, msg: str, *, force: bool = False, **kwargs: Any
    ) -> None:
        """Log a success message once."""
        if msg in self._logged_once:
            return
        self._logged_once.add(msg)
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        self.success(msg, force=force, stack_offset=stack_offset, **kwargs)

    def success(self, msg: str, *, force: bool = False, **kwargs: Any) -> None:
        """Log a success message if the verbosity level for success messages is enabled."""
        if not self.verbosity["success"] and not force:
            return
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        if JSON_FORMATTER:
            self.log_json(
                msg, stack_offset=stack_offset + 1, level="success", **kwargs
            )
            return
        self.log(
            self.get_modes()["success"].format(msg),
            stack_offset=stack_offset,
            force=force,
            **kwargs,
        )

    def error(self, msg: str, *, force: bool = False, **kwargs: Any) -> None:
        """Log an error message if the verbosity level for errors is enabled."""
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        if not self.verbosity["error"] and not force:
            return
        if JSON_FORMATTER:
            self.log_json(
                msg, stack_offset=stack_offset + 1, level="error", **kwargs
            )
            return
        self.log(
            self.get_modes()["error"].format(msg),
            stack_offset=stack_offset,
            force=force,
            **kwargs,
        )

    def warning_once(
        self, msg: str, *, force: bool = False, **kwargs: Any
    ) -> None:
        """Log a warning message once."""
        if msg in self._logged_once:
            return
        self._logged_once.add(msg)
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        self.warning(msg, force=force, stack_offset=stack_offset, **kwargs)

    def warning(self, msg: str, *, force: bool = False, **kwargs: Any) -> None:
        """Log a warning message if the verbosity level for warnings is.

            enabled.

        Arguments:
            msg (str): The warning message to be logged.
            force (bool): Whether to log the message regardless of the verbosity level.
            **kwargs: Additional keyword arguments that can be passed to the log method.

        Returns:
            None: This function does not return any value.

        Example:
            >>> log_warning("This is a warning message", verbosity_level=2)

        Note:
            The verbosity level for warnings is controlled by the
                'verbosity_level' keyword argument. If it is not
            provided, the default level is used.

        """
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        if not self.verbosity["warning"] and not force:
            return
        if JSON_FORMATTER:
            self.log_json(
                msg, stack_offset=stack_offset + 1, level="warning", **kwargs
            )
            return
        self.log(
            self.get_modes()["warning"].format(msg),
            stack_offset=stack_offset,
            force=force,
            **kwargs,
        )

    def info_once(
        self, msg: str, *, force: bool = False, **kwargs: Any
    ) -> None:
        """Log an informational message once."""
        if msg in self._logged_once:
            return
        self._logged_once.add(msg)
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        self.info(msg, force=force, stack_offset=stack_offset, **kwargs)

    def info(self, msg: str, *, force: bool = False, **kwargs: Any) -> None:
        """Log an informational message with the specified message."""
        if not self.verbosity["info"] and not force:
            return None
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += self.stack_offset + 1
        if JSON_FORMATTER:
            self.log_json(
                msg, stack_offset=stack_offset, level="info", **kwargs
            )
            return None
        return self.log(
            self.get_modes()["info"].format(msg),
            stack_offset=stack_offset,
            force=force,
            **kwargs,
        )

    def __jsonize(self, msg: str) -> str:
        """JSONize a message and add color formatting.

        Arguments:
            msg (str): A valid JSON string to format

        Returns:
            str: Formatted JSON string with Rich color markup

        Raises:
            JSONDecodeError: If input is not valid JSON

        Example:
            >>> msg = '{"name": "John", "age": 30, "active": true}'
            >>> logger.__jsonize(msg)
            {
                [blue]"name"[/blue]: [gold3]"John"[/gold3],
                [blue]"age"[/blue]: [gold3]30[/gold3],
                [blue]"active"[/blue]: [gold3]true[/gold3]
            }

            When printed with Rich, this will display as colored JSON with:
            - Keys in blue
            - String values in gold3
            - Numbers in gold3
            - Booleans/null in gold3

        """
        # Parse and reformat with consistent indentation
        jsonize = json.dumps(json.loads(msg), indent=4)
        # Color the keys blue and values gold3 in the JSON string
        jsonize = re.sub(r'(".*?"): ', r"[blue]\1[/blue]: ", jsonize)
        jsonize = re.sub(r': (".*?")', r": [gold3]\1[/gold3]", jsonize)
        jsonize = re.sub(
            r": ([-+]?\d*\.?\d+)", r": [gold3]\1[/gold3]", jsonize
        )
        jsonize = re.sub(
            r": (true|false|null)", r": [gold3]\1[/gold3]", jsonize
        )
        return jsonize.replace("\\n", "\n")

    def info_json(
        self, msg: str, *, force: bool = False, **kwargs: Any
    ) -> None:
        """Log an informational message in JSON format.

        This method logs a message in JSON format.
        """
        if not self.verbosity["log"] and not force:
            return
        stack_offset = kwargs.pop("stack_offset", 0)
        self.info(
            "\n" + self.__jsonize(msg),
            stack_offset=stack_offset + 1,
            force=force,
            **kwargs,
        )

    def error_json(
        self, msg: str, *, force: bool = False, **kwargs: Any
    ) -> None:
        """Log an error message in JSON format.

        This method logs a message in JSON format.
        """
        if not self.verbosity["error"] and not force:
            return
        self.error("\n" + self.__jsonize(msg), **kwargs)

    @override_from_dotenv("LOG_DEBUG")
    def debug(self, msg: str, *, force: bool = False, **kwargs: Any) -> None:
        """Log debug messages with additional keyword arguments if debug."""
        if not self.verbosity["debug"] and not force:
            return
        stack_offset = kwargs.pop("stack_offset", 0)
        stack_offset += (
            self.stack_offset + 2
        )  # counting the override_from_dotenv decorator
        if JSON_FORMATTER:
            self.log_json(
                msg, stack_offset=stack_offset + 1, level="debug", **kwargs
            )
            return
        self.log(
            self.get_modes()["debug"].format(msg),
            stack_offset=stack_offset,
            force=force,
            **kwargs,
        )

    def convert_list_to_bullets(self, l_string: str) -> str:
        """Convert a string containing a list into a formatted string with bullets."""
        # convert list to bullets
        l_string = l_string.replace("[", "").replace("]", "")
        # each entry is separated with quotes
        l_list = l_string[1:-1].split("', '")
        l_string = "\n".join([f"- {x}" for x in l_list])
        return "\n" + l_string

    def preprocess_msg(self, msg: str) -> str:
        """Preprocess a given message by performing several transformations."""
        return msg
        # replace $HOME with ~ for interuser compatibility
        # msg = msg.replace(Path.cwd().as_posix(), ".")
        # return msg.replace(os.getenv("HOME", "~"), "~")

    def print_once(self, msg: Any, **kwargs: Any) -> None:
        """Print a preprocessed message to the console once."""
        key = str(msg)
        if key in self._logged_once:
            return
        self._logged_once.add(key)
        self.print(msg, **kwargs)

    def print(self, msg: Any, *, force: bool = False, **kwargs: Any) -> None:
        """Print a preprocessed message to the console."""
        if not self.verbosity["print"] and not force:
            return
        if isinstance(msg, str):
            msg = self.preprocess_msg(msg)
        for console in self._message_consoles:
            console.print(msg, **kwargs)

    def input(self, msg: str, **kwargs: Any) -> str:
        """Input a message to the console.

        This method takes a message as input and returns the input from the
            console.
        """
        if isinstance(msg, str):
            msg = self.preprocess_msg(msg)
        return self.console.input(msg, **kwargs)

    def log_json(
        self,
        msg: Any,
        /,
        *,
        level: str,
        force: bool = False,
        indent: int = 4,
        sort_keys: bool = True,
        **kwargs: Any,
    ) -> None:
        """Log a message in JSON format."""
        if not self.verbosity[level] and not force:
            return
        stack_offset = kwargs.pop("stack_offset", 0)
        filename, line_no, _ = self.console._caller_frame_info(stack_offset)
        with contextlib.suppress(ValueError):
            filename = Path(filename).relative_to(Path.cwd()).as_posix()
        data = {
            "filename": f"{filename}:{line_no}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": msg,
            "level": level.upper(),
        }
        if self.id:
            data["trace_id"] = self.id
        rendered_data = json.dumps(data)
        for console in self._message_consoles:
            console.print_json(
                rendered_data, indent=indent, sort_keys=sort_keys
            )

    def log(
        self,
        msg: Any,
        /,
        *,
        stack_offset: int | None = None,
        progress: Progress | None = None,
        force: bool = False,
        **kwargs: Any,
    ) -> None:
        """Log a message with an optional stack offset and additional keyword arguments."""
        if not self.verbosity["log"] and not force:
            return
        kwargs["_stack_offset"] = (
            self.stack_offset if stack_offset is None else stack_offset
        )
        if isinstance(msg, str):
            msg = self.preprocess_msg(msg)
        if JSON_FORMATTER:
            stack_offset = kwargs.pop("_stack_offset", 0) + 1
            self.log_json(
                msg, level="log", stack_offset=stack_offset, **kwargs
            )
            return
        _msg = self.get_modes()["log"].format(msg)
        if progress is not None and self._route.get() is None:
            kwargs["_stack_offset"] = (
                self.stack_offset if stack_offset is None else stack_offset + 1
            )
            progress.console._log_render.omit_repeated_times = (
                RICH_OMIT_REPEATED_TIMES
            )
            progress.console.log(_msg, **kwargs)
        else:
            for console in self._message_consoles:
                console.log(_msg, **kwargs)

    def log_unittest(
        self,
        msg: str,
        stack_offset: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Log a unit test message with a specified message and stack offset."""
        # log only to a file - no console output - means the Unittest is running
        # make double sure that the log file is set
        kwargs["_stack_offset"] = (
            self.stack_offset if stack_offset is None else stack_offset
        )
        msg = self.preprocess_msg(str(msg))
        if not self.is_file_enabled():
            return
        self.log(msg, **kwargs)

    def rule(self, msg: str, **kwargs: Any) -> None:
        """Log a message with rule-based formatting."""
        if not self.verbosity["rule"]:
            return
        msg = self.preprocess_msg(msg)
        for console in self._message_consoles:
            console.rule(msg, **kwargs)

    def print_exception(
        self,
        msg: str | None = None,
        stack_offset: int = 1,
        **kwargs: Any,
    ) -> None:
        """Print an error message and exception details if an exception is raised."""
        if msg is not None:
            self.error(msg, stack_offset=stack_offset)
        # check if already inside an exception
        if sys.exc_info()[0] is not None:
            for console in self._message_consoles:
                console.print_exception(**kwargs)

    def exception(
        self, msg: str, stack_offset: int = 1, **kwargs: Any
    ) -> None:
        """Log an exception message with a specified message and additional keyword arguments."""
        self.print_exception(msg, stack_offset=stack_offset + 1, **kwargs)

    def status(self, msg: str, **kwargs: Any) -> Any:
        """Display a status message along with any additional keyword arguments in the console."""
        return self.console.status(msg, **kwargs)

    @property
    def _message_consoles(self) -> tuple[Console, ...]:
        route = self._route.get()
        return (self.console,) if route is None else route

    @contextlib.contextmanager
    def route(
        self, *streams: TextIO, terminal: bool = True
    ) -> Iterator[LoggingRich]:
        """Route messages to open text streams and optionally the console.

        Each nested scope replaces the previous route for the current
        execution context. Exiting restores the previous route. Additional
        streams receive plain text and stay open. Interactive progress and
        prompts continue to use the logger's original console.
        """
        consoles = routed_consoles(self.console, streams, terminal=terminal)
        token = self._route.set(consoles)
        try:
            yield self
        finally:
            self._route.reset(token)

    def unittest_logger(self, file_str: str) -> None:
        """Initialize a console object for logging unit test results."""
        self.console = Console(
            file=Path(file_str).open("w"),
            no_color=True,
            emoji=False,
            log_time=False,
            width=200,
            log_path=False,
        )

    def temporal_file_logger(self, **kwargs: Any) -> None:
        """Create a temporary file with a .log extension and initialize a console object with it."""
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            encoding="utf-8",
            mode="w",
            suffix=".log",
        )
        self.console = Console(file=temp_file, **kwargs)

    def enable_dual_output(self, file_path: str | Path, **kwargs: Any) -> None:
        """Enable logging to both console and file simultaneously.

        Args:
            file_path: Path to the log file
            **kwargs: Additional arguments passed to Console constructor

        """
        mirror = StreamMirror(
            self.console,
            file_path,
            previous=self._stream_mirror,
            console_options=kwargs,
        )
        self._stream_mirror = mirror
        self.stdout_duplicator = mirror.duplicator
        self.console = mirror.console
        self.console._log_render.omit_repeated_times = RICH_OMIT_REPEATED_TIMES

    def disable_dual_output(self) -> None:
        """Disable logging to both console and file simultaneously."""
        mirror = self._stream_mirror
        if mirror is None:
            return
        self.stdout_duplicator = None
        self._stream_mirror = None
        self.console = mirror.original_console
        mirror.close()

    @contextlib.contextmanager
    def to_file(
        self,
        file_path: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Context-manager form of :meth:`enable_dual_output`.

        Mirror every log line to ``file_path`` for the duration of the
        ``with`` block, then restore console-only output on exit.

        Example:
            >>> with logger.to_file("step.log"):
            ...     logger.info("written to console AND step.log")

        """
        self.enable_dual_output(file_path, **kwargs)
        try:
            yield self
        finally:
            self.disable_dual_output()

    @contextlib.contextmanager
    def timed(self, description: str) -> Any:
        """Log how long a block of work takes.

        Logs ``▶ {description}`` on entry and
        ``✓ {description} — Hd : Hh : Mm : Ss`` on exit, using the
        :func:`get_elapsed_time` formatter.

        Example:
            >>> with logger.timed("train epoch"):
            ...     train_one_epoch()

        """
        self.info(f"▶ {description}")
        start = datetime.now(tz=timezone.utc)
        try:
            yield
        finally:
            elapsed = (datetime.now(tz=timezone.utc) - start).total_seconds()
            days, rem = divmod(elapsed, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, seconds = divmod(rem, 60)
            formatted = (
                f"{int(days):02d}d : {int(hours):02d}h : "
                f"{int(minutes):02d}m : {int(seconds):02d}s"
            )
            self.success(f"✓ {description} — {formatted}")

    def kv(self, **fields: Any) -> None:
        """Log a single line of key=value pairs at INFO level.

        Renders ``epoch=12 lr=3e-4 loss=0.21`` with the keys colored
        blue and values colored gold. Common pattern for ML training
        scripts where each step emits one structured line.

        Example:
            >>> logger.kv(epoch=12, lr=3e-4, loss=0.214)

        """
        pairs = " ".join(
            f"[blue]{k}[/blue]=[gold3]{v}[/gold3]" for k, v in fields.items()
        )
        self.info(pairs)

    def get_last_line(self, name: str, msg: str) -> str:
        """Read and format the last line from a file with colors and styles based on its content."""
        if not self.is_file_enabled():
            return ""

        log_file = (
            self.stdout_duplicator.file_handle
            if self.stdout_duplicator is not None
            else self.console.file
        )
        with Path(log_file.name).open(encoding="utf-8") as f:
            last_line = f.readlines()[-1].strip()
        splitname = last_line.split(msg)
        time = f"[cyan] {splitname[0]} [/cyan]" if len(splitname) > 1 else ""
        level = self.get_modes()[name].format("")
        filename = (
            splitname[1].split()[0] if len(splitname) > 1 else splitname[0]
        )
        filename = f"[dim italic]{filename}[/dim italic]"
        if time:
            color_msg = [time, level, msg, filename]
        else:
            color_msg = [level, msg, filename]
        return " ".join(color_msg)


def get_logger(
    verbosity: dict[str, bool] | None = None,
    *,
    stderr: bool = False,
) -> LoggingRich:
    """Return a cached logger with optional verbosity overrides and stderr."""
    levels = DEFAULT_VERBOSITY | (verbosity or {})
    return _get_cached_logger(frozenset(levels.items()), stderr=stderr)


@lru_cache(maxsize=128)
def _get_cached_logger(
    levels: frozenset[tuple[str, bool]], *, stderr: bool
) -> LoggingRich:
    return LoggingRich(verbosity=dict(levels), console=Console(stderr=stderr))
