"""Enforces the daily Data API budget per lane, counted in Pacific Time like YouTube's quota day."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from GameChatCollector.Operations.QuotaSettings import Lane, QuotaSettings

PACIFIC = ZoneInfo("America/Los_Angeles")


def to_quota_day(moment: datetime) -> date:
    """Returns the Pacific-time date that the quota of this moment is counted on."""
    return moment.astimezone(PACIFIC).date()


def find_next_reset(moment: datetime) -> datetime:
    """Returns the next quota reset (midnight Pacific Time) after the moment."""
    next_day = to_quota_day(moment) + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=PACIFIC)


class QuotaLedger(Protocol):
    """Persistent record of units spent per quota day and lane."""

    def load_usage(self, quota_day: date) -> dict[Lane, int]:
        """Returns units spent per lane on the quota day."""
        ...

    def record_usage(self, quota_day: date, lane: Lane, units: int) -> None:
        """Adds spent units."""
        ...


class QuotaExhaustedError(RuntimeError):
    """Raised when a call would exceed the lane's remaining budget."""


class QuotaBudget:
    """Guarantees each lane its share; after the release time, unused shares form one pool (served in lane order by the caller)."""

    def __init__(self, settings: QuotaSettings, ledger: QuotaLedger, profile: str | None = None) -> None:
        """Creates a budget.

        Args:
            settings: Quota settings.
            ledger: Where usage is persisted.
            profile: Lane profile overriding the active one (for example, "bootstrap").
        """
        self._settings = settings
        self._ledger = ledger
        self._profile = profile

    def remaining(self, lane: Lane, now: datetime) -> int:
        """Units the lane may still spend on the current quota day."""
        usage = self._ledger.load_usage(to_quota_day(now))
        pool = self._settings.spendable_units() - sum(usage.values())
        # after the release time any lane may draw on the remaining shared pool
        if now >= find_next_reset(now) - timedelta(hours=self._settings.release_hours_before_reset):
            return max(0, pool)
        own = self._settings.allotment(lane, self._profile) - usage.get(lane, 0)
        return max(0, min(own, pool))

    def spend(self, lane: Lane, units: int, now: datetime) -> None:
        """Records units if they fit, otherwise raises QuotaExhaustedError."""
        if units > self.remaining(lane, now):
            raise QuotaExhaustedError(f"{lane} has {self.remaining(lane, now)} units left, needs {units}")
        self._ledger.record_usage(to_quota_day(now), lane, units)
