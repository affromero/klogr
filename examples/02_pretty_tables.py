"""Tabular console output via LoggingTable.

Run with: uv run examples/02_pretty_tables.py
"""

from klogr import LoggingTable, get_logger

logger = get_logger()


def main() -> None:
    """Render a small training-progress table."""
    table = LoggingTable(
        title="training progress",
        columns=["epoch", "train_loss", "val_loss", "lr"],
        colors=["bold", "cyan", "cyan", "magenta"],
        rows=[
            ["1", "2.413", "2.501", "3.0e-4"],
            ["2", "1.928", "2.013", "3.0e-4"],
            ["3", "1.547", "1.781", "1.5e-4"],
            ["4", "1.302", "1.612", "1.5e-4"],
            ["5", "1.118", "1.508", "7.5e-5"],
        ],
    )

    logger.table(table)


if __name__ == "__main__":
    main()
