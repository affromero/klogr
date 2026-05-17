"""Rich-based logger: :class:`LoggingRich`, :class:`LoggingTable`, :func:`get_logger`."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
from dataclasses import field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

import dotenv
from dotenv import load_dotenv
from pydantic import ConfigDict
from pydantic.dataclasses import dataclass
from rich import progress
from rich.box import ROUNDED, Box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from typing import TypeVar

    from rich.progress import Progress

    _T = TypeVar("_T")

load_dotenv()
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


class StdoutDuplicator:
    """Duplicates stdout output to a file, stripping ANSI codes."""

    def __init__(self, original_stdout: TextIO, file_path: str | Path) -> None:
        """Initialize StdoutDuplicator.

        Args:
            original_stdout: The original stdout
            file_path: Path to the log file

        """
        self.original_stdout = original_stdout
        self.file_handle: TextIO = Path(file_path).open("w", encoding="utf-8")

    def write(self, data: str) -> int:
        """Write to both stdout and file (stripping colors from file)."""
        # Write to original stdout
        result = self.original_stdout.write(data)

        # Write to file, stripping ANSI codes
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_data = ansi_escape.sub("", data)
        self.file_handle.write(clean_data)
        self.file_handle.flush()

        return result

    def flush(self) -> None:
        """Flush both stdout and file."""
        self.original_stdout.flush()
        self.file_handle.flush()

    def close(self) -> None:
        """Close file handle."""
        self.file_handle.close()

    def __getattr__(self, name: str) -> Any:
        """Delegate other attributes to original stdout."""
        return getattr(self.original_stdout, name)


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
            env_value = dotenv.get_key(dotenv.find_dotenv(), env_var_name)
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


class IterationsPerSecondColumn(progress.ProgressColumn):
    """Iterations per second column."""

    def render(self, task: progress.Task) -> Text:
        """Render the iterations per second column."""
        speed = task.finished_speed or task.speed
        if speed is None:
            return Text("? it/s", style="progress.data.speed")
        return Text(f"{speed:.2f} it/s", style="progress.data.speed")


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

    stdout_duplicator: StdoutDuplicator | None = None
    """ Stdout duplicator for file output when enabled. """

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
        return self.console.file.name != "<stdout>"

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
        if total is None and hasattr(iterable, "__len__"):
            total = len(iterable)  # type: ignore[arg-type]

        console = kwargs.pop("console", self.console)
        with progress.Progress(
            "[progress.description]{task.description}",
            progress.BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            progress.MofNCompleteColumn(),
            progress.TimeRemainingColumn(),
            progress.TimeElapsedColumn(),
            IterationsPerSecondColumn(),
            console=console,
            transient=transient,
            refresh_per_second=1,
            **kwargs,
        ) as prog:
            task_id = prog.add_task(description, total=total)
            for item in iterable:
                yield item
                prog.update(task_id, advance=1)

    def progress(self) -> progress.Progress:
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
        return progress.Progress(
            "[progress.description]{task.description}",
            progress.BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            progress.MofNCompleteColumn(),
            progress.TimeRemainingColumn(),
            progress.TimeElapsedColumn(),
            IterationsPerSecondColumn(),
            console=self.console,
            refresh_per_second=1,  # bit slower updates
        )

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
        self.console.print(msg, **kwargs)

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
        # self.console.log(
        #     RichJSON(json.dumps(data), indent=4, sort_keys=True),
        #     **kwargs,
        # )
        self.console.print_json(
            json.dumps(data), indent=indent, sort_keys=sort_keys
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
        if progress is not None:
            kwargs["_stack_offset"] = (
                self.stack_offset if stack_offset is None else stack_offset + 1
            )
            progress.console._log_render.omit_repeated_times = (
                RICH_OMIT_REPEATED_TIMES
            )
            progress.console.log(_msg, **kwargs)
        else:
            self.console.log(_msg, **kwargs)

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
        if self.console.file.name == "<stdout>":
            return
        self.log(msg, **kwargs)

    def rule(self, msg: str, **kwargs: Any) -> None:
        """Log a message with rule-based formatting."""
        if not self.verbosity["rule"]:
            return
        msg = self.preprocess_msg(msg)
        self.console.rule(msg, **kwargs)

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
            self.console.print_exception(**kwargs)

    def exception(
        self, msg: str, stack_offset: int = 1, **kwargs: Any
    ) -> None:
        """Log an exception message with a specified message and additional keyword arguments."""
        self.print_exception(msg, stack_offset=stack_offset + 1, **kwargs)

    def status(self, msg: str, **kwargs: Any) -> Any:
        """Display a status message along with any additional keyword arguments in the console."""
        return self.console.status(msg, **kwargs)

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
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".log")
        self.console = Console(file=temp_file, **kwargs)

    def enable_dual_output(self, file_path: str | Path, **kwargs: Any) -> None:
        """Enable logging to both console and file simultaneously.

        Args:
            file_path: Path to the log file
            **kwargs: Additional arguments passed to Console constructor

        """
        # Close any existing stdout duplicator
        if self.stdout_duplicator:
            self.stdout_duplicator.close()
            # Restore original stdout
            sys.stdout = self.stdout_duplicator.original_stdout

        # Create stdout duplicator
        self.stdout_duplicator = StdoutDuplicator(sys.stdout, file_path)

        # Replace sys.stdout with the duplicator
        sys.stdout = self.stdout_duplicator

        # Recreate console to use the new stdout, forcing terminal mode for colors
        console_kwargs = kwargs.copy()
        console_kwargs["force_terminal"] = True
        self.console = Console(**console_kwargs)
        self.console._log_render.omit_repeated_times = RICH_OMIT_REPEATED_TIMES

    def disable_dual_output(self) -> None:
        """Disable logging to both console and file simultaneously."""
        if self.stdout_duplicator:
            self.stdout_duplicator.close()
            # Restore original stdout
            sys.stdout = self.stdout_duplicator.original_stdout
            self.stdout_duplicator = None

            # Recreate console with restored stdout
            self.console = Console()
            self.console._log_render.omit_repeated_times = (
                RICH_OMIT_REPEATED_TIMES
            )

    def get_last_line(self, name: str, msg: str) -> str:
        """Read and format the last line from a file with colors and styles based on its content."""
        if self.console.file.name == "<stdout>":
            return ""

        # return last line of file
        with Path(self.console.file.name, "r", encoding="utf-8").open() as f:
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


@lru_cache(maxsize=128)
def get_logger(
    verbosity: dict[str, bool] = DEFAULT_VERBOSITY,
) -> LoggingRich:
    """Return a cached :class:`LoggingRich` for the given verbosity."""
    return LoggingRich(verbosity=verbosity)
