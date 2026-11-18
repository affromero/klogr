"""Check plain and hyperlinked source locations in Rich terminal logs."""

import os
import re
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from rich.console import Console

from klogr import LoggingRich


class SourceLocationTests(TestCase):
    """Check opt-in rendering across terminal and file routes."""

    def test_plain_source_preserves_full_path_in_terminal_and_route(
        self,
    ) -> None:
        """Write an absolute location without an OSC 8 hyperlink."""
        terminal, log_file = StringIO(), StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal, force_terminal=True, no_color=False, width=200
            ),
            plain_source=True,
        )
        with (
            patch.dict(os.environ, {"TERM": "xterm-256color"}),
            logger.route(log_file),
        ):
            logger.log("test message", force=True)
        for output in (terminal.getvalue(), log_file.getvalue()):
            assert re.search(
                rf"{re.escape(str(Path(__file__).resolve()))}:\d+", output
            )
            assert "\x1b]8;" not in output

    def test_default_console_keeps_source_links(self) -> None:
        """Preserve Rich's existing link format by default."""
        terminal = StringIO()
        logger = LoggingRich(
            console=Console(
                file=terminal,
                force_terminal=True,
                no_color=False,
                width=200,
                color_system="standard",
            )
        )
        with patch.dict(os.environ, {"TERM": "xterm-256color"}):
            logger.log("test message", force=True)
        assert "\x1b]8;" in terminal.getvalue()
        assert f"file://{Path(__file__).resolve()}#" in terminal.getvalue()
