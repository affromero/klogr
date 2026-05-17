"""Progress bar that survives parallel work (ThreadPoolExecutor).

`rich.progress.track()` goes silent when iterated by a pool's `map`. The
`logger.track()` wrapper feeds the pool's outputs back through Rich so the bar
updates in real time.

Run with: uv run examples/03_progress_tracking.py
"""

import time
from concurrent.futures import ThreadPoolExecutor

from klogr import get_logger

logger = get_logger()


def slow_square(n: int) -> int:
    """Pretend to do real work."""
    time.sleep(0.05)
    return n * n


def main() -> None:
    """Process 200 items across 8 workers with a live progress bar."""
    items = list(range(200))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            logger.track(
                pool.map(slow_square, items),
                total=len(items),
                description="squaring",
            )
        )

    logger.success(f"processed {len(results)} items, sum={sum(results)}")


if __name__ == "__main__":
    main()
