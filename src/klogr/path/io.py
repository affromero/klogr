"""Filesystem mutation helpers (mkdir, remove, copy, move, read/write)."""

import os
import shutil
from pathlib import Path
from typing import IO, Any

from rich import print as pprint

from .ops import path_dirname
from .query import path_is_dir, path_is_file, path_rglob


def path_rename(path: str | Path, new_name: str | Path) -> None:
    """Rename a path."""
    Path(path).rename(new_name)


def path_symlink(
    src: str | Path,
    dst: str | Path,
    *,
    ignore_existing: bool = False,
) -> None:
    """Create a symbolic link. If the destination already exists, it will be ignored.

    This function creates a symbolic link at the specified destination.
    The source path is converted to an absolute path to avoid broken symlinks.

    Arguments:
        src (str | Path): The source path to create the symbolic link from.
        dst (str | Path): The destination path to create the symbolic link to.
        ignore_existing (bool): Whether to ignore the existing destination. Default is False.

    Returns:
        None: This function does not return any value.

    Example:
        >>> path_symlink("path/to/src", "path/to/dst")

    Note:
        This function is useful in creating a symbolic link.

    """
    dst_path = Path(dst)

    # Check if destination exists (including broken symlinks)
    if dst_path.is_symlink() or dst_path.exists():
        if ignore_existing:
            return
        # Remove broken symlink to allow recreation
        if dst_path.is_symlink() and not dst_path.exists():
            dst_path.unlink()
        else:
            msg = f"Destination already exists: {dst}"
            raise FileExistsError(msg)

    # Use absolute path for source to avoid broken symlinks
    src_abs = os.path.realpath(src)
    dst_path.symlink_to(src_abs)


def path_mkdir(
    path: str | Path,
    *,
    parents: bool = False,
    exist_ok: bool = False,
) -> None:
    """Create a directory.

    This function creates a directory at the specified path.

    Arguments:
        path (str | Path): The path to create the directory.
        parents (bool): Whether to create parent directories. Default is False.
        exist_ok (bool): Whether to raise an error if the directory exists.
            Default is False.

    Returns:
        None: This function does not return any value.

    Example:
        >>> mkdir("path/to/dir", parents=True, exist_ok=True)

    Note:
        This function is useful in creating a directory.

    """
    Path(path).mkdir(parents=parents, exist_ok=exist_ok)


def path_remove(
    path: str | Path, *, non_exist_ok: bool = False, verbose: bool = False
) -> None:
    """Remove a file or directory.

    This function removes the specified file or directory.

    Arguments:
        path (str | Path): The path to remove.
        non_exist_ok (bool): Whether to raise an error if the file or directory does not exist.
            Default is False.
        verbose (bool): Whether to print messages. Default is False.

    Returns:
        None: This function does not return any value.

    Example:
        >>> remove("path/to/file")

    Note:
        This function is useful in removing a file or directory.

    """
    if verbose:
        pprint(f"!!![bold red]Removing {path}")
    Path(path).unlink(missing_ok=non_exist_ok)


def path_remove_dir(
    path: str | Path,
    *,
    verbose: bool = False,
    non_exist_ok: bool = False,
    only_files: bool = False,
) -> None:
    """Remove a directory.

    This function removes the specified directory.

    Arguments:
        path (str | Path): The directory to remove.
        verbose (bool): Whether to print messages. Default is False.
        non_exist_ok (bool): Whether to raise an error if the directory does not exist.
            Default is False.
        only_files (bool): Whether to remove only the files in the directory, but not the directory itself. Default is False.

    Returns:
        None: This function does not return any value.

    Example:
        >>> remove_dir("path/to/dir")

    Note:
        This function is useful in removing a directory.

    """
    if path_is_dir(path):
        for file in path_rglob(path, pattern="*"):
            if verbose:
                pprint(f"!!![bold red]Removing {file}")
            if path_is_file(file):
                path_remove(file)
        if not only_files:
            shutil.rmtree(path)
    elif not non_exist_ok:
        msg = f"{path} is not a directory"
        raise ValueError(msg)


def path_copy(src: str | Path, dst: str | Path) -> str:
    """Copy a file or directory.

    This function copies the specified file or directory to the destination.

    Arguments:
        src (str | Path): The source file or directory to copy.
        dst (str | Path): The destination file or directory to copy to.

    Returns:
        None: This function does not return any value.

    Example:
        >>> copy("path/to/src", "path/to/dst")

    Note:
        This function is useful in copying a file or directory.

    """
    return str(shutil.copy(src, dst))


def path_copy_dir(src: str | Path, dst: str | Path) -> str:
    """Copy a directory.

    This function copies the specified directory to the destination.

    Arguments:
        src (str | Path): The source directory to copy.
        dst (str | Path): The destination directory to copy to.

    Returns:
        None: This function does not return any value.

    Example:
        >>> copy_dir("path/to/src", "path/to/dst")

    Note:
        This function is useful in copying a directory.

    """
    path_mkdir(path_dirname(dst), exist_ok=True, parents=True)
    return str(shutil.copytree(src, dst, symlinks=False, dirs_exist_ok=True))


def path_move(src: str | Path, dst: str | Path) -> str:
    """Move a file or directory.

    This function moves the specified file or directory to the destination.

    Arguments:
        src (str | Path): The source file or directory to move.
        dst (str | Path): The destination file or directory to move to.

    Returns:
        None: This function does not return any value.

    Example:
        >>> move("path/to/src", "path/to/dst")

    Note:
        This function is useful in moving a file or directory.

    """
    return str(shutil.move(src, dst))


def path_read_text(path: str | Path) -> str:
    """Read text from a file.

    This function reads text from the specified file.

    Arguments:
        path (str | Path): The path to read text from.

    Returns:
        str: The text read from the file.

    Example:
        >>> read_text("path/to/file")
        'text'

    Note:
        This function is useful in reading text from a file.

    """
    return Path(path).read_text()


def path_open(
    path: str | Path,
    mode: str = "r",
    *,
    newline: str | None = None,
    encoding: str | None = None,
) -> IO[Any]:
    """Open a file.

    This function opens the specified file.

    Arguments:
        path (str | Path): The path to open.
        mode (str): The mode to open the file in. Default is 'r'.
        newline (str | None): The newline character to use. Default is None.
        encoding (str | None): The encoding to use. Default is None.

    Returns:
        file: The opened file.

    Example:
        >>> open("path/to/file", "r")

    Note:
        This function is useful in opening a file.

    """
    return Path(path).open(mode, newline=newline, encoding=encoding)


def path_write_text(path: str | Path, text: str) -> None:
    """Write text to a file.

    This function writes text to the specified file.

    Arguments:
        path (str | Path): The path to write text to.
        text (str): The text to write to the file.

    Returns:
        None: This function does not return any value.

    Example:
        >>> write_text("path/to/file", "text")

    Note:
        This function is useful in writing text to a file.

    """
    Path(path).write_text(text)
