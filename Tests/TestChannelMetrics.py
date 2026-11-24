"""Tests of ChannelMetricsCalculator."""

from __future__ import annotations

from datetime import timedelta

from Factories import REFERENCE, build_channel, build_live, load_policy
from GameChatCollector.Selection.ChannelMetrics import ChannelMetricsCalculator, ObservationWindow, contain_kana


def test_contain_kana_ignores_kanji_and_symbols() -> None:
    assert contain_kana("【マイクラ】")
    assert contain_kana("あ")
    assert not contain_kana("原神 直播 ・ー")
    assert not contain_kana("[APEX] rank")


def test_calculate_counts_only_long_streams_inside_window() -> None:
    policy = load_policy()
    window = ObservationWindow.ending_at(REFERENCE.date(), policy.window_days)
    videos = [
        build_live("in_game", REFERENCE - timedelta(days=10)),
        build_live("in_talk", REFERENCE - timedelta(days=20), category_id=24, title="Just chatting"),
        build_live("too_short", REFERENCE - timedelta(days=5), minutes=10),
        build_live("too_old", REFERENCE - timedelta(days=181)),
        build_live("future", REFERENCE + timedelta(hours=1)),
    ]
    metrics = ChannelMetricsCalculator(policy).calculate(build_channel(), videos, window, uploads_read=5, is_playlist_truncated=False)
    assert metrics.live_stream_count == 2
    assert metrics.game_stream_count == 1
    assert metrics.kana_title_share == 0.5
    assert metrics.game_share == 0.5
    assert metrics.game_stream_hours == 2.0
    assert metrics.chat_replay_sample == ["in_game"]


def test_calculate_leaves_shares_undefined_without_live_streams() -> None:
    policy = load_policy()
    window = ObservationWindow.ending_at(REFERENCE.date(), policy.window_days)
    metrics = ChannelMetricsCalculator(policy).calculate(build_channel(), [], window, 0, False)
    assert metrics.kana_title_share is None
    assert metrics.game_share is None


def test_sample_is_reproducible_and_bounded() -> None:
    policy = load_policy()
    games = [build_live(f"v{i}", REFERENCE - timedelta(days=i + 1)) for i in range(20)]
    calculator = ChannelMetricsCalculator(policy)
    first = calculator.sample_chat_replay_videos(games)
    assert first == calculator.sample_chat_replay_videos(list(reversed(games)))
    assert len(first) == policy.criteria.c5_sample_size
