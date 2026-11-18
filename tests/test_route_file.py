"""Verify scoped path-based logging and its file ownership."""

import asyncio
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase

from klogr import FileMode, LoggingRich


class RouteFileTests(TestCase):
    """Exercise file creation modes and restoration of outer routes."""

    def test_exclusive_append_and_overwrite(self) -> None:
        """Apply the explicitly selected file creation mode."""
        logger = LoggingRich()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "route.log"
            with logger.route_file(
                path, mode=FileMode.EXCLUSIVE, terminal=False
            ):
                logger.print("first", force=True)
            try:
                with logger.route_file(path, mode=FileMode.EXCLUSIVE):
                    self.fail("Existing file should prevent opening the scope")
            except FileExistsError:
                pass
            with logger.route_file(path, mode=FileMode.APPEND, terminal=False):
                logger.print("second", force=True)
            assert path.read_text(encoding="utf-8") == "first\nsecond\n"
            with logger.route_file(
                path, mode=FileMode.OVERWRITE, terminal=False
            ):
                logger.print("replacement", force=True)
            assert path.read_text(encoding="utf-8") == "replacement\n"

    def test_exclusive_mode_preserves_symlink_and_outer_route(self) -> None:
        """Reject a symlink before replacing the current route."""
        logger = LoggingRich()
        outer = StringIO()
        with (
            TemporaryDirectory() as directory,
            logger.route(outer, terminal=False),
        ):
            target = Path(directory) / "missing"
            link = Path(directory) / "link"
            link.symlink_to(target)
            try:
                with logger.route_file(link, mode=FileMode.EXCLUSIVE):
                    self.fail("Symlink should prevent exclusive creation")
            except FileExistsError:
                pass
            logger.print("still routed", force=True)
            assert link.is_symlink()
            assert not target.exists()
        assert outer.getvalue() == "still routed\n"


class RouteFileTaskTests(IsolatedAsyncioTestCase):
    """Cover inherited scopes after the owning context exits."""

    async def test_child_uses_outer_route_after_file_scope_ends(self) -> None:
        """Avoid writing to the file after the owning context closes it."""
        logger = LoggingRich()
        outer = StringIO()
        resume = asyncio.Event()

        async def child() -> None:
            await resume.wait()
            logger.print("after", force=True)

        with (
            TemporaryDirectory() as directory,
            logger.route(outer, terminal=False),
        ):
            path = Path(directory) / "route.log"
            with logger.route_file(
                path, mode=FileMode.EXCLUSIVE, terminal=False
            ):
                logger.print("inside", force=True)
                task = asyncio.create_task(child())
            resume.set()
            await task
            assert path.read_text(encoding="utf-8") == "inside\n"
        assert outer.getvalue() == "after\n"
