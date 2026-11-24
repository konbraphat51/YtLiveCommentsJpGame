"""Tests of QuotaBudget and the per-lane priority rules."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from GameChatCollector.Operations.PriorityRules import (
    BackfillPriorityRule,
    BackfillState,
    DiscoveryItem,
    DiscoveryPriorityRule,
    EligibilityItem,
    EligibilityPriorityRule,
    EligibilityTier,
    OperationalItem,
    OperationalKind,
    OperationalPriorityRule,
)
from GameChatCollector.Operations.QuotaBudget import QuotaBudget, QuotaExhaustedError, find_next_reset, to_quota_day
from GameChatCollector.Operations.QuotaSettings import Lane, QuotaSettings

SETTINGS = QuotaSettings.load(Path(__file__).resolve().parents[1] / "Config" / "ApiQuota.yaml")
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)  # 04:00 PST


class MemoryLedger:
    def __init__(self) -> None:
        self.usage: dict[tuple[date, Lane], int] = {}

    def load_usage(self, quota_day: date) -> dict[Lane, int]:
        return {lane: units for (day, lane), units in self.usage.items() if day == quota_day}

    def record_usage(self, quota_day: date, lane: Lane, units: int) -> None:
        self.usage[(quota_day, lane)] = self.usage.get((quota_day, lane), 0) + units


def test_quota_day_follows_pacific_time() -> None:
    assert to_quota_day(NOW) == date(2026, 11, 24)
    assert to_quota_day(datetime(2026, 11, 24, 7, 59, tzinfo=UTC)) == date(2026, 11, 23)
    assert find_next_reset(NOW).astimezone(UTC) == datetime(2026, 11, 25, 8, 0, tzinfo=UTC)


def test_lane_is_limited_to_its_share_until_release() -> None:
    budget = QuotaBudget(SETTINGS, MemoryLedger())
    assert budget.remaining(Lane.L4_DISCOVERY, NOW) == 500
    budget.spend(Lane.L4_DISCOVERY, 500, NOW)
    with pytest.raises(QuotaExhaustedError):
        budget.spend(Lane.L4_DISCOVERY, 100, NOW)
    release = find_next_reset(NOW) - timedelta(hours=4)
    assert budget.remaining(Lane.L4_DISCOVERY, release) == 9500 - 500


def test_bootstrap_profile_reallocates_shares() -> None:
    budget = QuotaBudget(SETTINGS, MemoryLedger(), profile="bootstrap")
    assert budget.remaining(Lane.L3_ELIGIBILITY, NOW) == 6000
    assert budget.remaining(Lane.L2_BACKFILL, NOW) == 0


def test_operational_rule_orders_tiers_and_skips_undue() -> None:
    rule = OperationalPriorityRule(SETTINGS.priority, "s")
    items = [
        OperationalItem("new", OperationalKind.NEW_VIDEO, NOW - timedelta(hours=1)),
        OperationalItem("refetch", OperationalKind.FINAL_REFETCH, NOW - timedelta(hours=3)),
        OperationalItem("soon", OperationalKind.LIVE_CHECK, NOW + timedelta(minutes=10)),
        OperationalItem("later", OperationalKind.LIVE_CHECK, NOW + timedelta(hours=2)),
        OperationalItem("fresh_end", OperationalKind.FINAL_REFETCH, NOW - timedelta(minutes=30)),
    ]
    assert [i.video_id for i in rule.order(items, NOW)] == ["soon", "refetch", "new"]


def test_backfill_rule_gates_on_lowest_slice() -> None:
    rule = BackfillPriorityRule(SETTINGS.priority, "s")
    states = [BackfillState("a", 1, 5.0), BackfillState("b", 0, 9.0), BackfillState("c", 0, 2.0), BackfillState("d", 0, 1.0, has_more_history=False)]
    assert [s.channel_id for s in rule.order(states, NOW)] == ["c", "b"]


def test_eligibility_rule_round_robins_sources_and_respects_cooldown() -> None:
    rule = EligibilityPriorityRule(SETTINGS.priority, "s")
    items = [EligibilityItem(f"s{i}", EligibilityTier.NEW_CANDIDATE, "search") for i in range(3)]
    items += [EligibilityItem(f"c{i}", EligibilityTier.NEW_CANDIDATE, "csv") for i in range(2)]
    items.append(EligibilityItem("re", EligibilityTier.RE_EVALUATION, "search"))
    items.append(EligibilityItem("lang", EligibilityTier.RETRY, "search", NOW - timedelta(days=100), frozenset({"C1"})))
    items.append(EligibilityItem("size", EligibilityTier.RETRY, "search", NOW - timedelta(days=100), frozenset({"C4"})))
    ordered = [i.channel_id for i in rule.order(items, NOW)]
    assert ordered[0] == "re"
    assert ordered[-1] == "size" and "lang" not in ordered
    sources = [i.primary_source for i in rule.order(items, NOW)[1:5]]
    assert sources.count("csv") == 2 and sources.count("search") == 2


def test_discovery_rule_prefers_unsearched_points() -> None:
    rule = DiscoveryPriorityRule(SETTINGS.priority, "s")
    items = [DiscoveryItem(0, 1), DiscoveryItem(5, 0), DiscoveryItem(2, 0)]
    assert [i.point_index for i in rule.order(items, NOW)] == [2, 5, 0]
