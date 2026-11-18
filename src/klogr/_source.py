"""Render terminal source locations using Rich's log renderer."""

from typing import TYPE_CHECKING, Any

from rich._log_render import LogRender

if TYPE_CHECKING:
    from rich.console import Console
    from rich.table import Table


class PlainSourceRender(LogRender):
    """Leave an absolute path and line available for terminal link detection."""

    def __call__(self, *args: Any, **kwargs: Any) -> "Table":
        """Use the absolute path without embedding an OSC 8 hyperlink."""
        link = kwargs.get("link_path")
        if link:
            kwargs.update(path=link, link_path=None)
        return super().__call__(*args, **kwargs)


def enable_plain_source(console: "Console") -> None:
    """Install the source renderer with the console's current settings."""
    original = console._log_render
    if not isinstance(original, PlainSourceRender):
        console._log_render = PlainSourceRender(
            show_time=original.show_time,
            show_level=original.show_level,
            show_path=original.show_path,
            time_format=original.time_format,
            omit_repeated_times=original.omit_repeated_times,
            level_width=original.level_width,
        )
