"""Path helpers — same API for local paths and s3:// URIs.

Run with: uv run examples/05_path_helpers.py
"""

import tempfile

from klogr import get_logger
from klogr.path import (
    path_basename,
    path_dirname,
    path_exists,
    path_glob,
    path_is_s3,
    path_join,
    path_mkdir,
    path_write_text,
)

logger = get_logger()


def main() -> None:
    """Show local + S3 paths going through the same helpers."""
    logger.rule("local paths")

    with tempfile.TemporaryDirectory() as tmp:
        nested = path_join(tmp, "a", "b", "c")
        path_mkdir(nested, parents=True, exist_ok=True)

        path_write_text(path_join(nested, "hello.txt"), "world")
        path_write_text(path_join(nested, "data.json"), "{}")

        logger.info(f"exists: {path_exists(nested)}")
        logger.info(f"dirname: {path_dirname(nested)}")
        logger.info(f"basename: {path_basename(nested)}")
        logger.info(f"glob: {path_glob(path_join(nested, '*'))}")

    logger.rule("S3 paths (no network call — just URI handling)")

    s3_uri = "s3://my-bucket/datasets/train/images/0001.jpg"
    logger.info(f"is_s3:    {path_is_s3(s3_uri)}")
    logger.info(f"dirname:  {path_dirname(s3_uri)}")
    logger.info(f"basename: {path_basename(s3_uri)}")
    logger.info(
        f"join:     {path_join('s3://my-bucket', 'prefix', 'file.bin')}"
    )


if __name__ == "__main__":
    main()
