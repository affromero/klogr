# Changelog

All notable changes to klogr are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] — 2026-05-17

### Added

- README: documented `logger.enable_dual_output(file_path)` — one line
  to mirror every log line into a file in addition to the Rich console.
  Listed it in the "Why use it" overview too.

## [0.1.5] — 2026-05-17

### Added

- `LICENSE.md` (MIT). The previous 0.1.x releases had `license = "MIT"`
  declared in `pyproject.toml` but the actual LICENSE file wasn't in
  the repo, so the wheel shipped without the license text.

## [0.1.4] — 2026-05-17

### Fixed

- `sha256sum>=2024.4.26` → `sha256sum>=2022.6.11`. The 2024 lower bound
  broke `uv sync` on macOS (`hax-cv[mps]` split) where only the older
  `sha256sum` wheel is published. klogr only uses the long-stable
  `sha256sum.sha256sum()` function, available since the 2022 versions.

## [0.1.3] — 2026-05-17

PyPI rejected the name `klog` with `400 The name 'klog' isn't allowed.`
(likely too close to existing Linux/Go-ecosystem names). Renamed to
`klogr` — same project, one letter different.

### Changed

- Package renamed `klog` → `klogr`. GitHub repo also renamed from
  `affromero/klog` to `affromero/klogr`. Imports change accordingly:
  `from klog import X` → `from klogr import X`.
- README install instructions, badges, and layout diagram updated for
  the new name.

### Fixed

- README incorrectly claimed `get_cache_dir()` returns `~/.cache/klog`;
  it actually returns the XDG cache root directly. Updated the comment.

## [0.1.2] — 2026-05-15

CI/workflow fixes after 0.1.1 also failed PyPI upload with the same
`400 Bad Request`. Local wheels build cleanly with the SPDX license
metadata — the failure is somewhere in the upload step. This release
adds `twine check` and `twine upload --verbose` to surface the actual
error.

### Fixed

- `.github/workflows/publish.yml`: bump `actions/checkout` to v4,
  `actions/setup-python` to v5, pin Python to 3.12 (3.x picked 3.14
  which prints deprecation noise).
- Add `twine check` and METADATA dump steps so we can see what's in
  the wheel before upload.
- `twine upload --verbose --non-interactive` for actionable errors
  when the upload step itself fails.

## [0.1.1] — 2026-05-15

First successful PyPI upload. Fixes the 0.1.0 build that PyPI rejected
with `400 Bad Request`.

### Fixed

- `pyproject.toml` `license` field uses the SPDX expression
  (`license = "MIT"` + `license-files = ["LICENSE.md"]`) instead of the
  legacy `{text = "MIT"}` form that newer PyPI rejects.
- Drop redundant `License :: OSI Approved :: MIT License` classifier
  (the SPDX expression replaces it; PyPI rejects both together).
- Project URLs in `pyproject.toml` corrected from `github.com/afromero/...`
  to `github.com/affromero/...` (the actual GitHub handle).
- README ASCII diagram rewritten with ASCII-safe box characters
  (`+--+`, `-->`) instead of Unicode box-drawing + `▶`. The previous
  version rendered crooked in Markdown viewers that gave `▶` a wider
  glyph than expected.

## [0.1.0] — 2026-05-15

First release under the new name `klogr`. Previously published as `difflogtest`.

### Changed

- **Renamed package** from `difflogtest` to `klogr`. The old name described a snapshot-test framework that is no longer part of this package.
- **Flattened the module layout.** The old `difflogtest.logging.*` and `difflogtest.utils.*` sub-packages have been merged into top-level modules:
  - `difflogtest.logging.core` → `klogr.logger`
  - `difflogtest.logging.cache_tools` → `klogr.cache`
  - `difflogtest.utils.strings` → `klogr.time`
  - `difflogtest.utils.path` → `klogr.path/` (split into `ops`, `io`, `query`, `env`)
- `logger.info_json` now uses stdlib `json` instead of `json5` — Pydantic-emitted JSON doesn't need comment tolerance.

### Removed

- **Snapshot test framework** (`UnitTests`, `@register_unittest`, `LogReplacement`, `is_unittest_mode`, `run-unittests` CLI). Not maintained; rely on `pytest` directly.
- **`seed_everything`** — pixelcache ships its own; this one only existed for the snapshot framework.
- **`wait_seconds_bar`** — zero consumers.
- **`path_download_and_extract_tar`** — drops the `wget` dependency.
- **`is_file_changed`, `logfile_from_func`, `path_from_pattern`, `keep_local_data`** — snapshot-only path helpers.

### Dropped dependencies

- `tyro` (snapshot CLI)
- `pytz` (unused)
- `json5` (info_json rewritten to stdlib json)
- `torch`, `torchvision` (seed_everything was the only consumer)
- `wget` (download helper removed)
- `GitPython` (`is_file_changed` was the only consumer)

### Kept

- `get_logger`, `LoggingRich`, `LoggingTable`, `DEFAULT_VERBOSITY`
- `lru_cache`, `DisableableLRUCache`, `get_cache_dir`, `sha256sum`
- All path helpers consumed by Hax-CV (`path_join`, `path_exists`, `path_mkdir`, `path_open`, `path_glob`, `path_basename`, `path_dirname`, `path_stem`, `path_is_s3`, `path_absolute`, `path_abs`, `path_dotenv`, `path_home`, `path_expanduser`, `path_relative_to`, `path_resolve`, `path_replace_suffix`, `path_rstrip`, `path_write_text`, `path_read_text`, `path_listdir`, `path_remove`, `path_remove_dir`, `path_copy`, `path_copy_dir`, `path_move`, `path_rename`, `path_symlink`, `path_islink`, `path_lexists`, `path_is_dir`, `path_is_file`, `path_is_image_file`, `path_is_video_file`, `path_getmtime`, `path_stat`, `path_dir_empty`, `path_exists_and_not_empty`, `path_startswith`, `path_endswith`, `path_newest_dir`, `path_newest_file`, `path_rglob`, `path_s3_bucket_name`, `is_glob_pattern`, `expand_glob_to_temp_dir`)
- `get_elapsed_time`

### Migration

Replace every `from difflogtest...` import:

| Old | New |
|-----|-----|
| `from difflogtest import get_logger` | `from klogr import get_logger` |
| `from difflogtest import lru_cache, sha256sum` | `from klogr import lru_cache, sha256sum` |
| `from difflogtest.utils.path import path_X` | `from klogr.path import path_X` |
| `from difflogtest.logging.core import LoggingTable` | `from klogr import LoggingTable` |

If you depended on `@register_unittest`, `is_unittest_mode`, or `LogReplacement` — those are gone. Use `pytest` directly.
