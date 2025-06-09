"""Utility for standardized sleep/delay handling."""

from __future__ import annotations

from time import sleep as time_sleep

from ib_insync import IB


def wait(seconds: float, ib: IB | None = None) -> None:
    """Pause execution for the given number of seconds.

    When an ``IB`` instance is provided, use its non-blocking wait
    mechanism to keep the event loop responsive. Fallbacks to ``sleep``
    if ``waitOnUpdate`` is unavailable.
    """
    if ib is not None:
        if hasattr(ib, "waitOnUpdate"):
            ib.waitOnUpdate(seconds)
        elif hasattr(ib, "sleep"):
            ib.sleep(seconds)
        else:
            time_sleep(seconds)
    else:
        time_sleep(seconds)
