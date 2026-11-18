"""Environment-related path helpers (.env, home directory)."""

from pathlib import Path

from .ops import path_cwd, path_join
from .query import path_exists


def path_dotenv() -> str:
    """Get the path to the .env file."""
    file_env = path_join(path_cwd(), ".env")
    if not path_exists(file_env):
        msg = f"File {file_env} not found"
        raise FileNotFoundError(msg)
    return file_env


def path_home() -> str:
    """Get the home directory."""
    return str(Path.home())


def path_expanduser(path: str | Path) -> str:
    """Expand a path to include the user's home directory.

    This function expands the specified path to include the user's home
        directory.

    Arguments:
        path (str | Path): The path to expand.

    Returns:
        str: The expanded path.

    Example:
        >>> path_expanduser("~/Documents")
        '/home/user/Documents'

    Note:
        This function is useful in expanding a path to include the user's home directory.

    """
    return str(Path(path).expanduser())
