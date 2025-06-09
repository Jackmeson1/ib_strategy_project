"""Utility for standardized sleep/delay handling."""

from __future__ import annotations

from time import sleep as time_sleep

from ib_insync import IB


def wait(seconds: float, ib: IB | None = None) -> None:
    """Pause execution for the given number of seconds."""
    if ib is not None:
        wait_fn = getattr(ib, "waitOnUpdate", getattr(ib, "sleep", None))
        if wait_fn is not None:
            wait_fn(seconds)
        else:  # pragma: no cover - extremely unlikely
            time_sleep(seconds)
    else:
        time_sleep(seconds)
