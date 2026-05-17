"""Filesystem query helpers (exists, glob, stat, listdir)."""

import glob
import os
import tempfile
from pathlib import Path

from .ops import path_basename, path_join, path_relative_to

# Glob pattern characters
GLOB_CHARS = {"*", "?", "["}


def path_islink(path: str | Path) -> bool:
    """Return True iff path is a symbolic link."""
    return Path(path).is_symlink()


def path_lexists(path: str | Path) -> bool:
    """Return True for existing paths, including broken symbolic links."""
    return os.path.lexists(path)


def path_exists(path: str | Path) -> bool:
    """Check if a path exists.

    This function checks if the specified path exists.

    Arguments:
        path (str | Path): The path to check for existence.

    Returns:
        bool: True if the path exists, False otherwise.

    Example:
        >>> exists("path/to/file")
        True

    Note:
        This function is useful in checking if a path exists.

    """
    return Path(path).exists()


def path_is_dir(path: str | Path) -> bool:
    """Check if a path is a directory.

    This function checks if the specified path is a directory.

    Arguments:
        path (str | Path): The path to check if it is a directory.

    Returns:
        bool: True if the path is a directory, False otherwise.

    Example:
        >>> is_dir("path/to/dir")
        True

    Note:
        This function is useful in checking if a path is a directory.

    """
    return Path(path).is_dir()


def path_is_file(path: str | Path) -> bool:
    """Check if a path is a file.

    This function checks if the specified path is a file.

    Arguments:
        path (str | Path): The path to check if it is a file.

    Returns:
        bool: True if the path is a file, False otherwise.

    Example:
        >>> is_file("path/to/file")
        True

    Note:
        This function is useful in checking if a path is a file.

    """
    return Path(path).is_file() or Path(path).is_symlink()


def path_dir_empty(path: str | Path) -> bool:
    """Check if a directory is empty.

    This function checks if the specified directory is empty.

    Arguments:
        path (str | Path): The path to check if it is a directory.

    Returns:
        bool: True if the directory is empty, False otherwise.

    Example:
        >>> path_dir_empty("path/to/dir")

    Note:
        This function is useful in checking if a directory is empty.

    """
    if not path_exists(path):
        return False
    return not any(Path(path).iterdir())


def path_exists_and_not_empty(path: str | Path) -> bool:
    """Check if a path exists and is not empty."""
    return path_exists(path) and not path_dir_empty(path)


def path_getmtime(path: str | Path) -> float:
    """Get the modification time of a path."""
    return Path(path).stat().st_mtime


def path_glob(path: str | Path, *, sort: bool = True) -> list[str]:
    """Get a list of paths that match a pattern.

    This function returns a list of paths that match the specified pattern.

    Arguments:
        path (str | Path): The path to get a list of paths from.
        sort (bool): Whether to sort the paths. Default is False.

    Returns:
        list[str]: A list of paths that match the pattern.

    Example:
        >>> glob("path/to/*.txt")

    Note:
        This function is useful in getting a list of paths that match a pattern.

    """
    return sorted(glob.glob(str(path))) if sort else glob.glob(str(path))  # noqa: PTH207


def path_rglob(
    path: str | Path, *, pattern: str, sort: bool = True
) -> list[str]:
    """Get a list of paths that match a pattern recursively.

    This function returns a list of paths that match the specified pattern recursively.

    Arguments:
        path (str | Path): The path to get a list of paths from.
        pattern (str): The pattern to match.
        sort (bool): Whether to sort the paths. Default is True.

    Returns:
        list[str]: A list of paths that match the pattern recursively.

    Example:
        >>> rglob("path/to/**/*.txt")

    Note:
        This function is useful in getting a list of paths that match a pattern recursively.

    """
    if "*" in str(path):
        msg = "Path cannot contain * - use path_glob instead"
        raise ValueError(msg)
    path_rglob = [str(i) for i in Path(path).rglob(pattern)]
    return sorted(path_rglob) if sort else list(path_rglob)


def path_listdir(
    path: str | Path,
    /,
    *,
    include_hidden: bool = False,
    include_private: bool = False,
) -> list[str]:
    """List the contents of a directory.

    This function returns a list of the contents of the specified directory.

    Arguments:
        path (str | Path): The path to list the contents of.
        include_hidden (bool): Whether to include hidden files and directories.
            Default is False.
        include_private (bool): Whether to include private files and directories.
            Default is False.

    Returns:
        list[str]: A list of the contents of the specified directory.

    Example:
        >>> listdir("path/to/dir")

    Note:
        This function is useful in listing the contents of a directory.

    """
    dirs = [path_relative_to(i, path) for i in Path(path).iterdir()]
    if not include_hidden:
        dirs = [i for i in dirs if not i.startswith(".")]
    if not include_private:
        dirs = [i for i in dirs if not i.startswith("__")]
    return dirs


def path_newest_dir(_dir: str | Path, /) -> list[str]:
    """Retrieve the most recently modified directories within a specified directory.

    Arguments:
        _dir (str | Path): The path of the directory to be inspected.

    Returns:
        list[str]: A list of directory paths, sorted from newest to oldest by modification time.

    Example:
        >>> path_newest_dir("/home/user/Documents")
        ['/home/user/Documents/dir1', '/home/user/Documents/dir2']

    Note:
        If the specified directory does not contain any directories, a ValueError will be raised.

    """
    subdirs = path_listdir(_dir)
    subdirs = [path_join(_dir, d) for d in subdirs]
    dirs = [Path(d) for d in subdirs if path_is_dir(d)]
    if len(dirs) == 0:
        msg = f"No directory in {_dir}"
        raise ValueError(msg)
    dirs.sort(key=lambda x: path_stat(x).st_mtime)
    return [str(d) for d in dirs[::-1]]


def path_newest_file(
    _dir: str | Path,
    /,
    *,
    pattern: str,
) -> str:
    """Retrieve the most recently modified file within a specified directory.

    Arguments:
        _dir (str | Path): The directory to search for the most recently modified file.
        pattern (str): The pattern to match the files.

    Returns:
        str: The path to the most recently modified file.

    """
    files = [f for f in Path(_dir).glob(pattern) if f.is_file()]
    files.sort(key=lambda x: path_stat(x).st_mtime)
    return str(files[-1])


def path_stat(path: str | Path, /) -> os.stat_result:
    """Get the stat of a path."""
    return Path(path).stat()


def is_glob_pattern(path: str) -> bool:
    """Check if a path contains glob pattern characters.

    Arguments:
        path (str): Path string to check.

    Returns:
        bool: True if path contains *, ?, or [ characters.

    Example:
        >>> is_glob_pattern("data/*/images/*.jpg")
        True
        >>> is_glob_pattern("data/images/photo.jpg")
        False

    """
    return any(char in path for char in GLOB_CHARS)


def expand_glob_to_temp_dir(pattern: str, *, prefix: str = "glob_") -> str:
    """Expand glob pattern and create temp directory with symlinks.

    Creates a temporary directory containing symlinks to all files matching
    the glob pattern. Files are prefixed with zero-padded indices to preserve
    sort order when the directory is read.

    Arguments:
        pattern (str): Glob pattern to expand (e.g., "data/*/images/*.jpg").
        prefix (str): Prefix for the temporary directory name.

    Returns:
        str: Path to temporary directory containing symlinks to matched files.

    Raises:
        FileNotFoundError: If no files match the pattern.

    Example:
        >>> temp_dir = expand_glob_to_temp_dir("data/*/frames/*.jpg")
        >>> # temp_dir contains:
        >>> #   000000_frame1.jpg -> data/a/frames/frame1.jpg
        >>> #   000001_frame2.jpg -> data/b/frames/frame2.jpg

    """
    matched_files = path_glob(pattern, sort=True)
    if not matched_files:
        msg = f"No files match glob pattern: {pattern}"
        raise FileNotFoundError(msg)

    # Create temporary directory with symlinks
    temp_dir = tempfile.mkdtemp(prefix=prefix)
    for idx, file_path in enumerate(matched_files):
        # Use zero-padded index prefix to preserve sort order
        basename = path_basename(file_path)
        link_name = f"{idx:06d}_{basename}"
        link_path = path_join(temp_dir, link_name)
        os.symlink(file_path, link_path)

    return temp_dir
