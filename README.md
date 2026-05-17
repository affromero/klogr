<div align="center">

# klogr

**Batteries-included structured logger for Python data/ML projects — built on [Rich](https://github.com/Textualize/rich).**

[![PyPI](https://img.shields.io/pypi/v/klogr)](https://pypi.org/project/klogr/)
[![Downloads](https://img.shields.io/pypi/dm/klogr)](https://pypi.org/project/klogr/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://pypi.org/project/klogr/)
[![Publish](https://img.shields.io/github/actions/workflow/status/affromero/klogr/publish.yml?label=publish)](https://github.com/affromero/klogr/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/github/license/affromero/klogr)](https://github.com/affromero/klogr/blob/main/LICENSE.md)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-261230?logo=ruff)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/typing-mypy%20strict-blue)](http://mypy-lang.org/)
[![jaxtyping](https://img.shields.io/badge/shapes-jaxtyping-orange)](https://github.com/patrick-kidger/jaxtyping)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://docs.pydantic.dev/latest/)
[![Beartype](https://raw.githubusercontent.com/beartype/beartype-assets/main/badge/bear-ified.svg)](https://beartype.readthedocs.io)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/affromero/klogr/pulls)

</div>

```text
  get_logger()
       |
       v
  +---------------------------+
  |        LoggingRich        |
  +---------------------------+
  | .info  .success  .warning |  -->  Rich-formatted console
  | .error .debug    .rule    |       with auto file:line prefix
  | .track .print    .info_json|
  +---------------------------+

  plus, from the same package:

    @lru_cache  +  DisableableLRUCache  -->  cached calls,
                                             with a disable hook for tests
    path_join / path_exists / path_open      -->  local + s3:// transparent
    get_elapsed_time(seconds)                -->  "01d : 01h : 12m : 03s"
    sha256sum(path) / get_cache_dir()        -->  stable on-disk caching
```

`klogr` is what you reach for when stdlib `logging.basicConfig` doesn't cut it and `print()` feels gross. It wraps Python's `logging` module with `rich.logging.RichHandler` pre-configured, adds stacklevel awareness so every line shows where it came from, and ships a handful of helpers (caching, paths, timing) that show up in every ML/data project.

## Why use it

- **Drop-in `get_logger()`** — module-scoped, cached, zero setup. No `logging.basicConfig`, no handler wiring.
- **Stacklevel-aware** — every log line auto-prefixes with the caller's `file:line`. Stop hunting for which module shouted what.
- **`logger.track()`** — wraps `rich.progress.track()` and works inside `ThreadPoolExecutor` / `ProcessPoolExecutor` without going silent.
- **`logger.print()` / `logger.info_json()`** — pretty-print Pydantic models, dicts, JSON without piping through `print(json.dumps(..., indent=2))`.
- **`@lru_cache` with a disable hook** — flip an env var to bypass caching globally (handy for tests).
- **Path helpers that handle S3** — `path_join`, `path_exists`, `path_mkdir`, etc. work whether you pass `/tmp/foo` or `s3://bucket/foo`.
- **`get_elapsed_time(seconds)`** — formats float seconds as `00d : 01h : 12m : 03s`.
- **One-liner dual output** — `with logger.to_file("run.log"):` mirrors every log line to BOTH the Rich-formatted console AND the log file. Perfect for batch jobs.
- **Timed blocks** — `with logger.timed("train epoch"):` prints entry + exit + elapsed, no `time.perf_counter()` boilerplate.
- **`logger.exception("msg")`** — like stdlib `logging.exception` but the traceback is rendered by Rich.
- **`logger.kv(epoch=12, lr=3e-4)`** — one-line structured key=value logging for training loops.

## Install

```bash
uv add klogr
# or
pip install klogr
```

Requires Python ≥ 3.10. Runtime deps: `rich`, `pydantic`, `python-dotenv`, `beartype`, `jaxtyping`, `natsort`, `sha256sum`.

## Quickstart

```python
from klogr import get_logger

logger = get_logger()

logger.info("loaded %d samples", 1024)         # auto file:line prefix
logger.success("training converged")            # green check
logger.warning("validation loss plateaued")
logger.error("OOM on batch 42")

# Pretty-print structured data
logger.print({"epoch": 12, "lr": 3e-4, "loss": 0.21})

# Progress bar that works in parallel
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=8) as pool:
    for result in logger.track(pool.map(process, items), total=len(items), description="batch"):
        ...
```

## What's in the box

### Logger

```python
from klogr import get_logger, LoggingRich, DEFAULT_VERBOSITY

logger = get_logger()                            # default verbosity
quiet  = get_logger({"info": False, "debug": False})  # custom

logger.info(msg)            # cyan
logger.success(msg)         # green check
logger.warning(msg)         # yellow
logger.error(msg)           # red
logger.rule(title)          # horizontal divider
logger.print(any_object)    # rich.print, soft-wrap aware
logger.info_json(json_str)  # syntax-colored JSON
logger.track(iter, total, description)  # progress bar
```

### Log to console AND a file at the same time

```python
from klogr import get_logger

logger = get_logger()

# Scoped to a block — auto-restores console-only on exit:
with logger.to_file("step.log"):
    logger.info("written to console AND step.log")
    logger.success("step done")
# back to console-only here

# Or set/unset manually if you need broader control:
logger.enable_dual_output("training.log")
logger.info("epoch=12")
logger.disable_dual_output()
```

The file gets the Rich-rendered output verbatim (colors stripped on the
file side, preserved in the terminal). Check `logger.is_file_enabled()`
to confirm dual output is on.

### Time a block

```python
with logger.timed("train epoch"):
    train_one_epoch()
# logs:  ▶ train epoch
#        ✓ train epoch — 00d : 00h : 12m : 03s
```

### Structured key=value lines

```python
logger.kv(epoch=12, lr=3e-4, loss=0.214)
# logs:  epoch=12 lr=0.0003 loss=0.214  (with rich coloring)
```

### Log an exception with a Rich traceback

```python
try:
    do_work()
except Exception:
    logger.exception("do_work failed")
# logs the message at ERROR, then a syntax-highlighted traceback
```

### Caching

```python
from klogr import lru_cache, DisableableLRUCache, get_cache_dir, sha256sum

@lru_cache(maxsize=128)
def expensive(key: str) -> bytes:
    ...

# Stable on-disk paths
cache_root = get_cache_dir()                          # XDG cache root
digest     = sha256sum("/path/to/file.bin")           # hex string
```

### Path helpers (local + S3 transparent)

```python
from klogr.path import (
    path_join, path_exists, path_mkdir, path_dirname,
    path_basename, path_glob, path_is_s3, path_open,
)

path_exists("/tmp/local.bin")       # True/False
path_exists("s3://bucket/key.bin")  # True/False (same call)
path_mkdir("/tmp/nested/dir", parents=True, exist_ok=True)
for p in path_glob("/data/*.jpg"):
    with path_open(p, "rb") as f:
        ...
```

### Timing

```python
from klogr import get_elapsed_time

print(get_elapsed_time(86400 + 3661))   # '01d : 01h : 01m : 01s'
```

## Examples

Runnable scripts live in [`examples/`](examples/):

- [`01_basic_logger.py`](examples/01_basic_logger.py) — log levels, formatting, file:line prefix
- [`02_pretty_tables.py`](examples/02_pretty_tables.py) — `LoggingTable` for tabular console output
- [`03_progress_tracking.py`](examples/03_progress_tracking.py) — `logger.track()` in parallel workers
- [`04_caching.py`](examples/04_caching.py) — `@lru_cache` with disable-hook
- [`05_path_helpers.py`](examples/05_path_helpers.py) — local + S3 path ops

```bash
uv run examples/01_basic_logger.py
```

## Layout

```
klogr/
├── __init__.py     # public re-exports
├── logger.py       # LoggingRich, LoggingTable, get_logger
├── cache.py        # lru_cache, DisableableLRUCache, sha256sum, get_cache_dir
├── path/           # local + S3 path helpers
│   ├── __init__.py
│   ├── ops.py      # pure ops (join, dirname, basename, suffix, …)
│   ├── env.py      # path_dotenv, path_home, path_expanduser
│   ├── io.py       # mkdir, remove, copy, move, read/write
│   └── query.py    # exists, is_dir, glob, listdir, stat
└── time.py         # get_elapsed_time
```

## Build & test

```bash
uv sync
.venv/bin/pre-commit run --all-files
.venv/bin/pytest
.venv/bin/mypy klogr/
```

## License

MIT — see [LICENSE.md](LICENSE.md).
