# Examples

Runnable scripts demonstrating each surface of `klogr`. Run any one with:

```bash
uv run examples/<name>.py
```

| File | What it shows |
|------|---------------|
| [`01_basic_logger.py`](01_basic_logger.py) | Log levels (info/success/warning/error), the auto file:line prefix, and pretty-printing of dicts + JSON. |
| [`02_pretty_tables.py`](02_pretty_tables.py) | `LoggingTable` for rendering tabular data to the console. |
| [`03_progress_tracking.py`](03_progress_tracking.py) | `logger.track()` keeping a live progress bar over a `ThreadPoolExecutor.map(...)`. |
| [`04_caching.py`](04_caching.py) | `@lru_cache` speedup, plus `get_cache_dir` and `sha256sum` for stable on-disk paths. |
| [`05_path_helpers.py`](05_path_helpers.py) | Local + `s3://` paths flowing through the same `path_*` helpers. |
