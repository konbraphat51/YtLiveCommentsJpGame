"""Tests of criteria C1-C6."""

from __future__ import annotations

from pathlib import Path

from Factories import build_channel, load_policy
from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics
from GameChatCollector.Selection.ChannelTypeScreener import ChannelTypeReviewBook, ChannelTypeScreener
from GameChatCollector.Selection.EligibilityCriteria import CriterionOutcome, build_default_criteria


def build_metrics(**overrides: object) -> ChannelMetrics:
    values: dict[str, object] = dict(subscriber_count=10000, is_subscriber_count_hidden=False, is_made_for_kids=False, live_stream_count=10, game_stream_count=8, kana_title_share=0.8, game_share=0.3)
    values.update(overrides)
    return ChannelMetrics(**values)  # type: ignore[arg-type]


def judge(metrics: ChannelMetrics) -> dict[str, CriterionOutcome]:
    policy = load_policy()
    return {c.criterion_id: c.check(metrics, policy).outcome for c in build_default_criteria()}


def test_thresholds_are_inclusive() -> None:
    outcomes = judge(build_metrics())
    assert [outcomes[k] for k in ("C1", "C2", "C3", "C4")] == [CriterionOutcome.PASS] * 4
    assert outcomes["C5"] == CriterionOutcome.PENDING


def test_values_below_thresholds_fail() -> None:
    outcomes = judge(build_metrics(kana_title_share=0.79, game_stream_count=7, game_share=0.29, subscriber_count=9999, chat_replay_share=0.4))
    assert set(outcomes.values()) == {CriterionOutcome.FAIL}


def test_undefined_values_fail() -> None:
    outcomes = judge(build_metrics(kana_title_share=None, game_share=None, subscriber_count=None))
    assert outcomes["C1"] == outcomes["C3"] == outcomes["C4"] == CriterionOutcome.FAIL


def test_channel_type_flags_and_reviews(tmp_path: Path) -> None:
    policy = load_policy()
    screener = ChannelTypeScreener(policy, ChannelTypeReviewBook({}))
    assert screener.check(build_channel(title="ぺこら 切り抜き")).outcome == CriterionOutcome.PENDING
    assert screener.check(build_channel(title="Game Official")).outcome == CriterionOutcome.PENDING
    assert screener.check(build_channel(is_made_for_kids=True)).outcome == CriterionOutcome.FAIL
    assert screener.check(build_channel(title="普通の配信者")).outcome == CriterionOutcome.PASS
    review_path = tmp_path / "Reviews.csv"
    review_path.write_text("channel_id,decision,reason,reviewer,reviewed_at\nUCxxxxxxxxxxxxxxxxxxxxxx,PASS,individual streamer,me,2026-11-24\n", encoding="utf-8")
    reviewed = ChannelTypeScreener(policy, ChannelTypeReviewBook.load(review_path))
    assert reviewed.check(build_channel(title="ぺこら 切り抜き")).outcome == CriterionOutcome.PASS
