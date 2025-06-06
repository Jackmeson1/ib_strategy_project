from __future__ import annotations

"""Utility for standardized sleep/delay handling."""
from time import sleep as time_sleep
from typing import Optional

from ib_insync import IB


def wait(seconds: float, ib: Optional[IB] = None) -> None:
    """Pause execution for the given number of seconds."""
    if ib is not None:
        ib.sleep(seconds)
    else:
        time_sleep(seconds)
