"""Regression tests for console streams and log files."""

import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from klogr import get_logger


class LoggerStreamTests(TestCase):
    """Exercise stream selection and file mirroring through the public API."""

    check_equal = TestCase.assertEqual

    def test_default_logger_writes_to_stdout(self) -> None:
        """Route default log output to stdout."""
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            get_logger().print("default stream")
        self.check_equal(stdout.getvalue(), "default stream\n")
        self.check_equal(stderr.getvalue(), "")

    def test_stderr_logger_leaves_json_on_stdout(self) -> None:
        """Keep stdout parseable as JSON when the logger writes to stderr."""
        logger = get_logger(stderr=True)
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            logger.print("diagnostic")
            self.check_equal(logger.is_file_enabled(), second=False)
            print(json.dumps({"records": 12}))
        self.check_equal(json.loads(stdout.getvalue()), {"records": 12})
        self.check_equal(stderr.getvalue(), "diagnostic\n")

    def test_context_mirrors_each_stream_and_restores_it_on_error(
        self,
    ) -> None:
        """Save plain text and restore the selected stream after exceptions."""
        for use_stderr in (False, True):
            with (
                self.subTest(stderr=use_stderr),
                TemporaryDirectory() as directory,
            ):
                log_file = Path(directory) / "run.log"
                logger = get_logger(stderr=use_stderr)
                stdout, stderr = StringIO(), StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    try:
                        with logger.to_file(
                            log_file, color_system="standard", no_color=False
                        ):
                            self.check_equal(
                                logger.is_file_enabled(), second=True
                            )
                            logger.print("mirrored", style="red")
                            error = "interrupted"
                            raise RuntimeError(error)
                    except RuntimeError as exc:
                        self.check_equal(str(exc), "interrupted")
                    else:
                        self.fail("Expected the exception to propagate")
                    self.check_equal(sys.stdout is stdout, second=True)
                    self.check_equal(sys.stderr is stderr, second=True)
                    self.check_equal(logger.is_file_enabled(), second=False)
                    logger.print("after")
                selected, other = (
                    (stderr, stdout) if use_stderr else (stdout, stderr)
                )
                self.check_equal("\x1b[" in selected.getvalue(), second=True)
                self.check_equal(
                    selected.getvalue().endswith("after\n"), second=True
                )
                self.check_equal(other.getvalue(), "")
                self.check_equal(
                    log_file.read_text(encoding="utf-8"), "mirrored\n"
                )

    def test_manual_mirroring_keeps_stdout_available(self) -> None:
        """Mirror stderr writes until dual output is disabled."""
        logger = get_logger(stderr=True)
        stdout, stderr = StringIO(), StringIO()
        with (
            TemporaryDirectory() as directory,
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            log_file = Path(directory) / "run.log"
            logger.enable_dual_output(log_file)
            try:
                logger.print("logged")
                print("stderr write", file=sys.stderr)
                print(json.dumps({"ok": True}))
            finally:
                logger.disable_dual_output()
            self.check_equal(sys.stderr is stderr, second=True)
            self.check_equal(
                log_file.read_text(encoding="utf-8"), "logged\nstderr write\n"
            )
        self.check_equal(stderr.getvalue(), "logged\nstderr write\n")
        self.check_equal(json.loads(stdout.getvalue()), {"ok": True})
