"""Tests for atomic text replacement."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from klogr.path import path_write_text_atomic


class AtomicTextWriteTests(TestCase):
    """Check the destination and its parent after atomic writes."""

    def test_replacement_preserves_encoding_and_line_endings(self) -> None:
        """Replace an existing file with the exact encoded text."""
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            destination = parent / "manifest.json"
            destination.write_bytes(b"previous")

            path_write_text_atomic(destination, "é\r\n", encoding="latin-1")

            assert destination.read_bytes() == b"\xe9\r\n"
            assert list(parent.iterdir()) == [destination]

    def test_failed_write_preserves_destination_and_cleans_up(self) -> None:
        """Keep the previous file when an encoding error interrupts a write."""
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            destination = parent / "manifest.json"
            destination.write_bytes(b"previous")

            try:
                path_write_text_atomic(destination, "é", encoding="ascii")
            except UnicodeEncodeError:
                pass
            else:
                self.fail("Expected an encoding error")

            assert destination.read_bytes() == b"previous"
            assert list(parent.iterdir()) == [destination]

    def test_failed_replace_preserves_destination_and_cleans_up(self) -> None:
        """Keep the previous file when the filesystem rejects replacement."""
        with TemporaryDirectory() as directory:
            parent = Path(directory)
            destination = parent / "manifest.json"
            destination.write_bytes(b"previous")

            with patch.object(Path, "replace", side_effect=PermissionError):
                try:
                    path_write_text_atomic(destination, "replacement")
                except PermissionError:
                    pass
                else:
                    self.fail("Expected a filesystem error")

            assert destination.read_bytes() == b"previous"
            assert list(parent.iterdir()) == [destination]
