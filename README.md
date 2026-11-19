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

`klogr` uses Rich consoles to render log messages and their source locations.
It also provides caching, path, and timing helpers.

## Why use it

- **Drop-in `get_logger()`** — module-scoped, cached, zero setup. No `logging.basicConfig`, no handler wiring.
- **Stacklevel-aware** — every log line auto-prefixes with the caller's `file:line`. Stop hunting for which module shouted what.
- **`logger.track()`** — wraps `rich.progress.track()` and works inside `ThreadPoolExecutor` / `ProcessPoolExecutor` without going silent.
- **`logger.print()` / `logger.info_json()`** — pretty-print Pydantic models, dicts, JSON without piping through `print(json.dumps(..., indent=2))`.
- **`@lru_cache` with a disable hook** — flip an env var to bypass caching globally (handy for tests).
- **Path helpers** for local file operations and for manipulating URI strings.
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

![Terminal demo of klogr log levels and formatted data](https://raw.githubusercontent.com/affromero/klogr/main/docs/media/logging.gif)

```python
from klogr import get_logger

logger = get_logger()

logger.info(f"loaded {1024} samples")           # adds the source location
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

Use `get_logger(stderr=True)` when stdout carries JSON or other machine-readable
data. By default, logs go to stdout. Both streams normally appear in the
terminal. Redirect stdout to a file or pipe it to another command to process the
data separately.

```python
import json

from klogr import get_logger

logger = get_logger(stderr=True)
logger.info("Processed 12 records")
print(json.dumps({"records": 12}))
```

### Route messages to open streams

```python
import json

from klogr import get_logger

logger = get_logger(stderr=True)
with open("command.log", "x", encoding="utf-8") as log:
    with logger.route(log):
        logger.info("Processed 12 records")
    print(json.dumps({"records": 12}))
```

`route()` renders messages to the logger's console and each supplied stream.
Files receive plain text. Pass `terminal=False` to write only to the supplied
streams. Use `get_logger(stderr=True)` for commands that reserve stdout for data.

An inner route replaces the outer route until it exits. Routes are local to
the current execution context, so concurrent tasks can use the same logger
with different destinations. The caller opens and closes each stream.
Interactive progress and prompts use the logger's console.

![Terminal demo of a progress bar tracking parallel work](https://raw.githubusercontent.com/affromero/klogr/main/docs/media/progress.gif)

Use `logger.route_file(path, mode=FileMode.EXCLUSIVE)` when the scope should
open and close the file. Import `FileMode` from `klogr` and choose
`EXCLUSIVE`, `APPEND`, or `OVERWRITE`. Exclusive mode preserves existing
files and symlinks. This API routes logger messages. The existing `to_file()`
also mirrors direct writes to the selected standard stream.

### Track several operations in one dashboard

Use `logger.live_dashboard()` with `DashboardRow` to update operations by
key. The interactive display shows elapsed time and shares the terminal
with `status()`, `timed_status()`, and progress bars. Redirected and file
destinations receive each changed row and a final summary.

![Live capacity search with region rows and a shared status spinner](https://raw.githubusercontent.com/affromero/klogr/main/docs/media/region-dashboard.gif)

```bash
uv run examples/07_region_dashboard.py
```

Use one outer live scope per console. Async tasks on the owning thread
can update its rows. The optional `render` callback receives a row snapshot
on the Rich render thread.

### Report stage and frame progress

![Live dashboard showing decode and score stages and their output files](https://raw.githubusercontent.com/affromero/klogr/main/docs/media/dashboard.gif)

The [dashboard example](examples/06_live_dashboard.py) renders a table of stage
statuses, frame counts, and elapsed times. It also writes `run.log` and
`events.jsonl` to the directory you pass in.

```bash
uv run examples/06_live_dashboard.py logs/demo
```

```python
from klogr import FileMode, ProgressEvent, ProgressStatus, get_logger

logger = get_logger(stderr=True)
with (
    logger.route_file("run.log", mode=FileMode.EXCLUSIVE),
    open("events.jsonl", "x", encoding="utf-8") as events,
    logger.progress_events(jsonl=events) as publish,
):
    publish(ProgressEvent(
        stage="generate", status=ProgressStatus.STARTED, elapsed_seconds=0,
    ))
    publish(ProgressEvent(
        stage="frames", status=ProgressStatus.RUNNING, elapsed_seconds=1.5,
        completed=10, total=60,
    ))
```

Each JSON Lines record has `stage`, `status`, `elapsed_seconds`, `completed`,
and `total`. The count fields are null when omitted. Supply a separate stream
for JSON Lines. Text logs throttle repeated running updates per stage and
retain transitions, completion, and failure. Pass a `dashboard` callback
that returns a Rich renderable to customize the interactive terminal display.
Redirected sessions and file sinks receive plain progress lines.

Inside an interactive dashboard scope, `logger.track()` and
`logger.progress()` add progress bars to the same live display.
`logger.print()` and other log methods still write to the active text
destinations. JSON Lines records come from events passed to `publish()`.

### Format a training metrics table

![Terminal recording of a training metrics table with colored columns](https://raw.githubusercontent.com/affromero/klogr/main/docs/media/table.gif)

Use `LoggingTable` to set the title, column names, colors, and rows. The
[table example](examples/02_pretty_tables.py) shows five epochs of training
and validation loss.

```bash
uv run examples/02_pretty_tables.py
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

Both methods mirror writes to the logger's selected stream. The file receives
plain text and the terminal keeps its colors. Exiting `to_file` or calling
`disable_dual_output()` restores the original stream.

### Time a block

```python
with logger.timed("train epoch"):
    train_one_epoch()
# logs:  ▶ train epoch
#        ✓ train epoch — 00d : 00h : 12m : 03s
```

### Show a timed status while waiting

For a long-running wait, use `timed_status()` to display a spinner and an
elapsed timer. Call `wait.update("pending")` when the remote status changes.
The terminal keeps updating the clock between polls.

```python
with logger.timed_status("Creating image", entry=True, interval=30) as wait:
    wait.update("pending")
    wait.update("running", percent=60)
```

`interval` throttles plain-text updates from `update()`. Leave it unset
for entry and outcome messages only. The default follows the logger's
INFO verbosity. Use `enabled=False` for a quiet scope. Completion reports
success, failure, or cancellation. A supplied `service_eta` is labeled
as such. Use `logger.progress()` when you have a reliable total and want
Rich's calculated estimate. Timed waits can share an active dashboard and
nest or overlap in asyncio tasks on one logger. Keep status updates on the
owning thread.

### Open source locations in an editor

Set `get_logger(plain_source=True)` to expose absolute `path:line` locations
for terminal link detection. For long paths, give the source column enough
terminal width. Rich hyperlinks remain the default.

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

### Local files and URI strings

```python
from klogr.path import (
    path_join, path_exists, path_mkdir, path_dirname,
    path_basename, path_glob, path_is_s3, path_open,
)

path_exists("/tmp/local.bin")       # True/False
path_dirname("s3://bucket/key.bin") # s3://bucket
path_mkdir("/tmp/nested/dir", parents=True, exist_ok=True)
for p in path_glob("/data/*.jpg"):
    with path_open(p, "rb") as f:
        ...
```

Use `path_write_text_atomic()` from `klogr.path` to publish a local text
file or serialized manifest. It writes a sibling temporary file and
replaces the destination after the write and close succeed.

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
src/klogr/
├── __init__.py     # public re-exports
├── logger.py       # LoggingRich, LoggingTable, get_logger
├── _progress.py    # shared Rich progress rendering
├── _streams.py     # scoped destinations and legacy stream mirroring
├── cache.py        # lru_cache, DisableableLRUCache, sha256sum, get_cache_dir
├── path/           # local filesystem and URI helpers
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
uv run pre-commit install --install-hooks
uv run pre-commit run --all-files
uv run python -m unittest discover -v
uv run mypy --strict --follow-untyped-imports src/klogr tests
```

## License

MIT — see [LICENSE.md](LICENSE.md).
