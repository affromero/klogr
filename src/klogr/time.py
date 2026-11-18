"""Time-formatting helpers."""


def get_elapsed_time(elapsed_time: float) -> str:
    """Convert elapsed time from seconds to a formatted string.

    This function takes in a float value representing elapsed time in
        seconds and
    converts it into a formatted string displaying the elapsed time in the
        format
    'dd : hh : mm : ss'.

    Arguments:
        elapsed_time (float): The elapsed time in seconds.

    Returns:
        str: A formatted string displaying the elapsed time in the format
            'dd : hh : mm : ss'.

    Example:
        >>> format_time(3661.0)
        '00 : 01 : 01 : 01'
    Note:
        The input elapsed_time should be a non-negative float number.

    """
    days, rem = divmod(elapsed_time, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{int(days):02d}d : {int(hours):02d}h : {int(minutes):02d}m : {int(seconds):02d}s"
