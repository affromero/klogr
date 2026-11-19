"""klogr — batteries-included structured logger built on Rich.

Public API. Most users want :func:`get_logger`. Path helpers live under
:mod:`klogr.path`.
"""

from ._dashboard import Dashboard, DashboardRow, DashboardState
from ._streams import FileMode
from .cache import (
    DisableableLRUCache,
    get_cache_dir,
    lru_cache,
    sha256sum,
)
from .events import ProgressEvent, ProgressStatus
from .logger import (
    DEFAULT_VERBOSITY,
    LoggingRich,
    LoggingTable,
    get_logger,
)
from .time import get_elapsed_time

__all__ = [
    "DEFAULT_VERBOSITY",
    "Dashboard",
    "DashboardRow",
    "DashboardState",
    "DisableableLRUCache",
    "FileMode",
    "LoggingRich",
    "LoggingTable",
    "ProgressEvent",
    "ProgressStatus",
    "get_cache_dir",
    "get_elapsed_time",
    "get_logger",
    "lru_cache",
    "sha256sum",
]
