"""@lru_cache with a disable hook (helpful for testing).

Run with: uv run examples/04_caching.py
"""

import time

from klogr import get_cache_dir, get_logger, lru_cache, sha256sum

logger = get_logger()


@lru_cache(maxsize=128)
def fib(n: int) -> int:
    """Naive recursive Fibonacci, cached so subsequent calls are O(1)."""
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def main() -> None:
    """Demonstrate cache hit speedup + cache directory location."""
    logger.rule("cache speedup")

    t0 = time.perf_counter()
    fib(30)
    cold = time.perf_counter() - t0

    t0 = time.perf_counter()
    fib(30)
    warm = time.perf_counter() - t0

    logger.info(f"cold call: {cold * 1000:.2f} ms")
    logger.info(f"warm call: {warm * 1000:.2f} ms")
    logger.success(f"speedup: {cold / max(warm, 1e-9):.0f}x")

    logger.rule("cache utilities")
    logger.info(f"get_cache_dir(): {get_cache_dir()}")
    logger.info(f"sha256sum(__file__): {sha256sum(__file__)[:16]}…")


if __name__ == "__main__":
    main()
