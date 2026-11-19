"""Show a simulated capacity search with retries across regions."""

from time import sleep

from rich.text import Text

from klogr import DashboardRow, DashboardState, get_logger


def main() -> None:
    """Update each region as the search advances."""
    logger = get_logger()
    with logger.live_dashboard("Capacity search") as dashboard:
        for region in ("us-east-1", "us-west-2", "eu-west-1"):
            dashboard.update_row(region, DashboardRow(name=region))
        with logger.status(Text("Checking capacity", style="cyan")) as status:
            dashboard.update_row(
                "us-east-1",
                DashboardRow(
                    name="us-east-1", state=DashboardState.RUNNING, attempts=1
                ),
            )
            sleep(0.7)
            dashboard.update_row(
                "us-east-1",
                DashboardRow(
                    name="us-east-1",
                    state=DashboardState.FAILED,
                    attempts=1,
                    error="No capacity",
                ),
            )
            dashboard.update_row(
                "us-west-2",
                DashboardRow(
                    name="us-west-2", state=DashboardState.RUNNING, attempts=2
                ),
            )
            status.update(Text("Retrying in us-west-2", style="cyan"))
            logger.info("Retry scheduled in us-west-2")
            sleep(0.9)
            dashboard.update_row(
                "us-west-2",
                DashboardRow(
                    name="us-west-2",
                    state=DashboardState.SUCCEEDED,
                    attempts=2,
                ),
            )
            dashboard.update_row(
                "eu-west-1",
                DashboardRow(name="eu-west-1", state=DashboardState.SKIPPED),
            )
            sleep(0.7)


if __name__ == "__main__":
    main()
