"""Criteria C1-C6 of the channel policy, each judging one aspect of ChannelMetrics."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy


class CriterionOutcome(StrEnum):
    """Result of one criterion."""

    PASS = "PASS"
    FAIL = "FAIL"
    # The value has not been measured yet (for example, C5 needs watch pages).
    PENDING = "PENDING"


@dataclass(frozen=True)
class CriterionResult:
    """Outcome of one criterion with the measured value it was based on."""

    criterion_id: str
    outcome: CriterionOutcome
    value: float | int | str | None


class EligibilityCriterion(ABC):
    """One inclusion criterion; implementations must be pure functions of metrics and policy."""

    criterion_id: str = ""

    @abstractmethod
    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Judges the metrics against the policy."""

    def _judge(self, is_passed: bool, value: float | int | str | None) -> CriterionResult:
        """Builds a PASS or FAIL result."""
        return CriterionResult(self.criterion_id, CriterionOutcome.PASS if is_passed else CriterionOutcome.FAIL, value)


class JapaneseLanguageCriterion(EligibilityCriterion):
    """C1: share of live-stream titles that contain kana."""

    criterion_id = "C1"

    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Fails when no live stream exists, because the share is undefined."""
        share = metrics.kana_title_share
        return self._judge(share is not None and share >= policy.criteria.c1_min_kana_title_share, share)


class GameStreamCountCriterion(EligibilityCriterion):
    """C2: number of completed public game live streams in the window."""

    criterion_id = "C2"

    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Compares the game stream count with the minimum."""
        return self._judge(metrics.game_stream_count >= policy.criteria.c2_min_game_streams, metrics.game_stream_count)


class GameShareCriterion(EligibilityCriterion):
    """C3: game streams divided by all completed live streams."""

    criterion_id = "C3"

    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Fails when no live stream exists."""
        share = metrics.game_share
        return self._judge(share is not None and share >= policy.criteria.c3_min_game_share, share)


class SubscriberCountCriterion(EligibilityCriterion):
    """C4: subscriber count on the reference date; hidden counts fail."""

    criterion_id = "C4"

    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Compares the subscriber count with the minimum."""
        count = metrics.subscriber_count
        return self._judge(count is not None and count >= policy.criteria.c4_min_subscribers, count)


class ChatReplayCriterion(EligibilityCriterion):
    """C5: share of sampled game streams with chat replay; PENDING until watch pages are checked."""

    criterion_id = "C5"

    def check(self, metrics: ChannelMetrics, policy: ChannelPolicy) -> CriterionResult:
        """Returns PENDING when the sample has not been checked yet."""
        share = metrics.chat_replay_share
        if share is None:
            return CriterionResult(self.criterion_id, CriterionOutcome.PENDING, None)
        return self._judge(share >= policy.criteria.c5_min_chat_replay_share, share)


def build_default_criteria() -> list[EligibilityCriterion]:
    """Returns the metric-based criteria C1-C5 in order (C6 is judged by ChannelTypeScreener)."""
    return [JapaneseLanguageCriterion(), GameStreamCountCriterion(), GameShareCriterion(), SubscriberCountCriterion(), ChatReplayCriterion()]


# Criteria that rarely change; a failure on them gets the long re-evaluation cooldown.
STABLE_CRITERION_IDS = frozenset({"C1", "C6"})
