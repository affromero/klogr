"""Basic logger — levels, formatting, and the file:line auto-prefix.

Run with: uv run examples/01_basic_logger.py
"""

from klogr import get_logger

logger = get_logger()


def main() -> None:
    """Print one of each log level so you can eyeball the styling."""
    logger.rule("level demo")

    logger.info("plain info message")
    logger.success("operation succeeded")
    logger.warning("something looks off")
    logger.error("hit an error path")

    logger.rule("structured output")

    config = {"epoch": 12, "lr": 3e-4, "loss": 0.214, "best": True}
    logger.print(config)

    logger.info_json('{"event": "checkpoint", "step": 100, "loss": 0.21}')


if __name__ == "__main__":
    main()
