from dataclasses import dataclass
from datetime import date
from typing import Protocol


class Clock(Protocol):
    def today(self) -> date: ...


class SystemClock:
    def today(self) -> date:
        return date.today()


@dataclass(frozen=True)
class FixedClock:
    day: date

    def today(self) -> date:
        return self.day


def get_clock() -> Clock:
    """FastAPI dependency; override in tests with a FixedClock."""
    return SystemClock()
