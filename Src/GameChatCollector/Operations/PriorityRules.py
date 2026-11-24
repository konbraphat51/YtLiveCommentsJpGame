"""Sort keys that order work inside each Data API lane; popularity is never part of any key."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum

from GameChatCollector.Operations.QuotaSettings import PrioritySettings
from GameChatCollector.Selection.ChannelMetrics import hash_salted
from GameChatCollector.Selection.EligibilityCriteria import STABLE_CRITERION_IDS


class PriorityRule[ItemT](ABC):
    """Orders the work items of one lane; smaller keys run first."""

    def __init__(self, settings: PrioritySettings, salt: str) -> None:
        """Creates a rule.

        Args:
            settings: Priority parameters from Config/ApiQuota.yaml.
            salt: Salt of the tie-breaking hash.
        """
        self._settings = settings
        self._salt = salt

    @abstractmethod
    def sort_key(self, item: ItemT, now: datetime) -> tuple[object, ...] | None:
        """Returns the key, or None if the item is not runnable now."""

    def order(self, items: list[ItemT], now: datetime) -> list[ItemT]:
        """Returns the runnable items in priority order."""
        keyed = [(key, item) for item in items if (key := self.sort_key(item, now)) is not None]
        return [item for _, item in sorted(keyed, key=lambda pair: pair[0])]


class OperationalKind(IntEnum):
    """L1 work kinds; the value is the tier."""

    LIVE_CHECK = 0
    FINAL_REFETCH = 1
    NEW_VIDEO = 2


@dataclass(frozen=True)
class OperationalItem:
    """L1 work on one video."""

    video_id: str
    kind: OperationalKind
    # LIVE_CHECK: scheduled start; FINAL_REFETCH: actualEndTime; NEW_VIDEO: discovery time
    reference_time: datetime
    is_live: bool = False


class OperationalPriorityRule(PriorityRule[OperationalItem]):
    """L1: imminent or live streams, then due final refetches, then new videos oldest first."""

    def sort_key(self, item: OperationalItem, now: datetime) -> tuple[object, ...] | None:
        """Returns (tier, reference_time, hash), or None while the item is not due."""
        if item.kind is OperationalKind.LIVE_CHECK and not item.is_live and item.reference_time - now > timedelta(minutes=self._settings.imminent_minutes):
            return None
        if item.kind is OperationalKind.FINAL_REFETCH and now - item.reference_time < timedelta(hours=self._settings.grace_hours):
            return None
        return (int(item.kind), item.reference_time, hash_salted(item.video_id, self._salt))


@dataclass(frozen=True)
class BackfillState:
    """L2 progress of one cohort channel."""

    channel_id: str
    # slice k covers [now - (k+1)*slice_days, now - k*slice_days); this is the next slice to collect
    next_slice_index: int
    collected_game_hours: float
    has_more_history: bool = True


class BackfillPriorityRule(PriorityRule[BackfillState]):
    """L2: time-sliced round-robin; only channels on the lowest open slice run, fewest collected hours first."""

    def order(self, items: list[BackfillState], now: datetime) -> list[BackfillState]:
        """Returns the channels allowed to backfill now, in order."""
        open_items = [s for s in items if s.has_more_history]
        if not open_items:
            return []
        lowest = min(s.next_slice_index for s in open_items)
        return super().order([s for s in open_items if s.next_slice_index == lowest], now)

    def sort_key(self, item: BackfillState, now: datetime) -> tuple[object, ...] | None:
        """Returns (slice, collected hours, hash)."""
        return (item.next_slice_index, item.collected_game_hours, hash_salted(item.channel_id, self._salt))


class EligibilityTier(IntEnum):
    """L3 tiers."""

    RE_EVALUATION = 0
    NEW_CANDIDATE = 1
    RETRY = 2


@dataclass(frozen=True)
class EligibilityItem:
    """L3 work: measuring one candidate."""

    channel_id: str
    tier: EligibilityTier
    # the source that found the candidate first; round-robin runs across these
    primary_source: str
    last_failed_at: datetime | None = None
    failed_criteria: frozenset[str] = frozenset()


class EligibilityPriorityRule(PriorityRule[EligibilityItem]):
    """L3: re-evaluations, then new candidates round-robin across sources, then retries after their cooldown."""

    def is_cooled_down(self, item: EligibilityItem, now: datetime) -> bool:
        """Returns True if a failed candidate may be measured again."""
        if item.last_failed_at is None:
            return True
        is_stable = bool(item.failed_criteria & STABLE_CRITERION_IDS)
        days = self._settings.stable_failure_cooldown_days if is_stable else self._settings.variable_failure_cooldown_days
        return now - item.last_failed_at >= timedelta(days=days)

    def order(self, items: list[EligibilityItem], now: datetime) -> list[EligibilityItem]:
        """Assigns round-robin ranks within each source and tier, then sorts."""
        runnable = [i for i in items if i.tier is not EligibilityTier.RETRY or self.is_cooled_down(i, now)]
        groups: dict[tuple[EligibilityTier, str], list[EligibilityItem]] = {}
        for item in runnable:
            groups.setdefault((item.tier, item.primary_source), []).append(item)
        keyed: list[tuple[tuple[object, ...], EligibilityItem]] = []
        for (tier, source), members in groups.items():
            members.sort(key=lambda i: hash_salted(i.channel_id, self._salt))
            keyed += [((int(tier), rank, source), item) for rank, item in enumerate(members)]
        return [item for _, item in sorted(keyed, key=lambda pair: pair[0])]

    def sort_key(self, item: EligibilityItem, now: datetime) -> tuple[object, ...] | None:
        """Single-item key without round-robin rank (order() is authoritative)."""
        if item.tier is EligibilityTier.RETRY and not self.is_cooled_down(item, now):
            return None
        return (int(item.tier), hash_salted(item.channel_id, self._salt))


@dataclass(frozen=True)
class DiscoveryItem:
    """L4 work: one point of the search frame."""

    point_index: int
    times_searched: int


class DiscoveryPriorityRule(PriorityRule[DiscoveryItem]):
    """L4: points never searched first, then by their fixed index in the low-discrepancy sequence."""

    def sort_key(self, item: DiscoveryItem, now: datetime) -> tuple[object, ...] | None:
        """Returns (times searched, point index)."""
        return (item.times_searched, item.point_index)
