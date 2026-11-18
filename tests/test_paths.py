"""Exercise file removal against a real temporary filesystem."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from klogr.path import path_remove_dir, path_rstrip


class RemoveDirectoryTests(TestCase):
    """Keep external directory targets intact."""

    def test_directory_symlink_is_rejected_before_removing_files(self) -> None:
        """Preserve files when the requested directory is a symlink."""
        with TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.mkdir()
            data = target / "data.txt"
            data.write_text("keep", encoding="utf-8")
            link = Path(directory) / "link"
            link.symlink_to(target, target_is_directory=True)

            for only_files in (False, True):
                with self.subTest(only_files=only_files):
                    try:
                        path_remove_dir(link, only_files=only_files)
                    except ValueError:
                        pass
                    else:
                        self.fail(
                            "Expected a directory symlink to be rejected"
                        )
                    assert data.read_text(encoding="utf-8") == "keep"
                    assert link.is_symlink()

    def test_removing_tree_does_not_follow_nested_directory_symlinks(
        self,
    ) -> None:
        """Remove a tree containing a symlink without touching its target."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.mkdir()
            data = target / "data.txt"
            data.write_text("keep", encoding="utf-8")
            tree = root / "tree"
            tree.mkdir()
            nested_link = tree / "link"
            nested_link.symlink_to(target, target_is_directory=True)

            path_remove_dir(tree)

            assert not tree.exists()
            assert data.read_text(encoding="utf-8") == "keep"

    def test_only_files_leaves_directories_in_place(self) -> None:
        """Recursively remove regular files while keeping their directories."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            data = nested / "data.txt"
            data.write_text("remove", encoding="utf-8")

            path_remove_dir(root, only_files=True)

            assert nested.is_dir()
            assert not data.exists()


class SuffixTests(TestCase):
    """Exercise literal path suffix handling."""

    def test_removes_only_the_requested_suffix(self) -> None:
        """Preserve trailing stem letters and ignore a nonmatching suffix."""
        assert path_rstrip("report.txt", ".txt") == "report"
        assert path_rstrip("report.csv", ".txt") == "report.csv"
