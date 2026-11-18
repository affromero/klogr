"""Pure path operations (no filesystem I/O)."""

import re
from pathlib import Path

_URI_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+\-.]*://")


def _has_uri_scheme(path: str) -> bool:
    """Check if path has a URI scheme (s3://, gs://, http://)."""
    return bool(_URI_SCHEME_RE.match(path))


def _uri_dirname(path: str) -> str:
    """Get parent directory of a URI path via string splitting."""
    path = path.rstrip("/")
    scheme_end = path.find("://")
    if scheme_end != -1:
        authority_start = scheme_end + 3
        last_slash = path.rfind("/")
        if last_slash <= authority_start:
            return path  # at or before bucket level
        return path[:last_slash]
    last_slash = path.rfind("/")
    return path[:last_slash] if last_slash != -1 else path


def get_suffix(path: str | Path) -> str:
    """Get the suffix of a path."""
    return Path(path).suffix


def path_replace_suffix(path: str | Path, suffix: str) -> str:
    """Replace the suffix of a path."""
    str_path = str(path)
    if suffix.startswith("."):
        if _has_uri_scheme(str_path):
            dirname = _uri_dirname(str_path)
            stem = Path(str_path).stem
            return f"{dirname}/{stem}{suffix}"
        return str(Path(path).with_suffix(suffix))
    dirname = path_dirname(path)
    basename = path_basename(path)
    return path_join(dirname, f"{basename}{suffix}")


def path_rstrip(path: str | Path, suffix: str) -> str:
    """Remove the suffix from a path."""
    return str(path).rstrip(suffix)


def path_resolve(path: str | Path) -> str:
    """Resolve a path."""
    return str(Path(path).resolve())


def path_join(*paths: str | Path) -> str:
    """Join multiple paths together.

    This function joins multiple paths together using the '/' separator.

    Arguments:
        *paths: str or Path. The paths to join.
        out (str): The output type. Default is 'str'.

    Returns:
        str or Path: The joined path.

    Example:
        >>> path_join("path", "to", "file", out="str")
        'path/to/file'

    Note:
        This function is useful in joining multiple paths together.

    """
    return "/".join([str(p) for p in paths])


def path_cwd() -> str:
    """Get the current working directory."""
    return str(Path.cwd())


def path_dirname(path: str | Path) -> str:
    """Get the directory name of a path.

    This function returns the directory name of the specified path.
    For URI paths (s3://, gs://, etc.), uses string splitting to
    preserve the scheme's double slash.

    Arguments:
        path (str | Path): The path to get the directory name from.

    Returns:
        str: The directory name of the specified path.

    Example:
        >>> path_dirname("path/to/file")
        'path/to'
        >>> path_dirname("s3://bucket/key/file.txt")
        's3://bucket/key'

    """
    str_path = str(path)
    if _has_uri_scheme(str_path):
        return _uri_dirname(str_path)
    return str(Path(path).parent)


def path_basename(path: str | Path) -> str:
    """Get the base name of a path.

    This function returns the base name of the specified path.

    Arguments:
        path (str | Path): The path to get the base name from.

    Returns:
        str: The base name of the specified path.

    Example:
        >>> basename("path/to/file.format")
        'file.format'

    Note:
        This function is useful in getting the base name of a path.

    """
    return Path(path).name


def path_stem(path: str | Path) -> str:
    """Get the stem of a path.

    This function returns the stem of the specified path.

    Arguments:
        path (str | Path): The path to get the stem from.

    Returns:
        str: The stem of the specified path.

    Example:
        >>> stem("path/to/file.format")
        'file'

    Note:
        This function is useful in getting the stem of a path.

    """
    return Path(path).stem


def path_relative_to(path: str | Path, base: str | Path) -> str:
    """Get the relative path of a path.

    This function returns the relative path of the specified path with respect to the base path.

    Arguments:
        path (str | Path): The path to get the relative path from.
        base (str | Path): The base path to get the relative path to.

    Returns:
        str: The relative path of the specified path with respect to the base path.

    Example:
        >>> path_relative_to("path/to/file", "path/to/")
        'file'

    Note:
        This function is useful in getting the relative path of a path.

    """
    return str(Path(path).absolute().relative_to(Path(base).absolute()))


def path_absolute(path: str | Path) -> str:
    """Get the absolute path of a path.

    This function returns the absolute path of the specified path.

    Arguments:
        path (str | Path): The path to get the absolute path from.

    Returns:
        str: The absolute path of the specified path.

    Example:
        >>> path_absolute("path/to/file")
        '/path/to/file'

    Note:
        This function is useful in getting the absolute path of a path.

    """
    return str(Path(path).absolute())


def path_abs(path: str | Path) -> str:
    """Get the absolute path of a path.

    This function returns the absolute path of the specified path.

    Arguments:
        path (str | Path): The path to get the absolute path from.

    Returns:
        str: The absolute path of the specified path.

    Example:
        >>> abs("path/to/file")
        '/path/to/file'

    Note:
        This function is useful in getting the absolute path of a path.

    """
    return str(Path(path).absolute())


def path_is_s3(path: str | Path) -> bool:
    """Check if a path is in S3."""
    return str(path).startswith("s3://")


def path_s3_bucket_name(path: str | Path) -> str:
    """Get the S3 bucket name from a path: s3://bucket/path/to/file."""
    if not path_is_s3(path):
        msg = f"Path {path} is not an S3 path."
        raise ValueError(msg)
    return str(path).split("://")[1].split("/")[0]


def path_startswith(path: str | Path, start: str) -> bool:
    """Check if a path starts with a string.

    This function checks if the specified path starts with the specified string.

    Arguments:
        path (str | Path): The path to check.
        start (str): The string to check if the path starts with.

    Returns:
        bool: True if the path starts with the string, False otherwise.

    Example:
        >>> startswith("path/to/file", "path")

    Note:
        This function is useful in checking if a path starts with a string.

    """
    return str(path).startswith(start)


def path_endswith(path: str | Path, end: str) -> bool:
    """Check if a path ends with a string.

    This function checks if the specified path ends with the specified string.

    Arguments:
        path (str | Path): The path to check.
        end (str): The string to check if the path ends with.

    Returns:
        bool: True if the path ends with the string, False otherwise.

    Example:
        >>> endswith("path/to/file", "file")

    Note:
        This function is useful in checking if a path ends with a string.

    """
    return str(path).endswith(end)


def path_is_image_file(path: str | Path) -> bool:
    """Check if a path is an image file."""
    return get_suffix(path).lower() in [
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".heic",
        ".heif",
        ".webp",
    ]


def path_is_video_file(path: str | Path) -> bool:
    """Check if a path is a video file."""
    return get_suffix(path).lower() in [
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm",
    ]
