"""Measures the quantities that criteria C1-C5 are judged on, from API snapshots only (pure logic)."""

from __future__ import annotations

import hashlib
import re
import statistics
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from GameChatCollector.Domain.Channel import ChannelSnapshot, VideoSnapshot
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy

# Hiragana (U+3041-U+3096) and katakana letters (U+30A1-U+30FA); excludes the middle dot and the prolonged sound mark.
KANA_PATTERN = re.compile(r"[ぁ-ゖァ-ヺ]")


def contain_kana(text: str) -> bool:
    """Returns True if the text contains at least one hiragana or katakana letter."""
    return KANA_PATTERN.search(text) is not None


def hash_salted(value: str, salt: str) -> str:
    """Returns the reproducible pseudo-random key hash(value + salt) used for ordering and sampling."""
    return hashlib.sha256((value + salt).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ObservationWindow:
    """The half-open UTC interval [start, end) over which a channel is measured."""

    start: datetime
    end: datetime

    @classmethod
    def ending_at(cls, reference_date: date, window_days: int) -> ObservationWindow:
        """Builds the window that ends at 00:00 UTC of the reference date."""
        end = datetime.combine(reference_date, time.min, tzinfo=UTC)
        return cls(start=end - timedelta(days=window_days), end=end)

    def contain(self, moment: datetime) -> bool:
        """Returns True if the moment lies in the window."""
        return self.start <= moment < self.end


@dataclass
class ChannelMetrics:
    """Measured values of one candidate on one reference date; serialized as metrics_json."""

    subscriber_count: int | None
    is_subscriber_count_hidden: bool
    is_made_for_kids: bool
    live_stream_count: int = 0
    game_stream_count: int = 0
    kana_title_share: float | None = None
    game_share: float | None = None
    game_stream_hours: float = 0.0
    median_game_stream_views: float | None = None
    last_game_stream_at: str | None = None
    uploads_read: int = 0
    is_playlist_truncated: bool = False
    chat_replay_sample: list[str] = field(default_factory=list)
    chat_replay_available: int | None = None
    chat_replay_share: float | None = None
    game_card_share: float | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Returns a JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> ChannelMetrics:
        """Restores metrics from metrics_json."""
        return cls(**data)


class ChannelMetricsCalculator:
    """Turns a channel snapshot and its uploads into ChannelMetrics, following the policy's classification rules."""

    def __init__(self, policy: ChannelPolicy) -> None:
        """Creates a calculator for one policy version.

        Args:
            policy: The channel policy whose classification rules are applied.
        """
        self._policy = policy

    def is_live_stream(self, video: VideoSnapshot, window: ObservationWindow) -> bool:
        """Returns True if the video is a completed live stream that started in the window and is long enough."""
        duration = video.live_duration_minutes
        if duration is None or video.actual_start is None:
            return False
        return window.contain(video.actual_start) and duration >= self._policy.classification.min_live_duration_minutes

    def is_game_stream(self, video: VideoSnapshot, window: ObservationWindow) -> bool:
        """Returns True if the video is a live stream in a game category."""
        return self.is_live_stream(video, window) and video.category_id in self._policy.classification.game_category_ids

    def calculate(self, channel: ChannelSnapshot, videos: list[VideoSnapshot], window: ObservationWindow, uploads_read: int, is_playlist_truncated: bool) -> ChannelMetrics:
        """Measures one channel.

        Args:
            channel: The channel snapshot from channels.list.
            videos: Every upload of the channel read for the window (any type).
            window: The observation window.
            uploads_read: Number of playlist items read.
            is_playlist_truncated: True if the page limit stopped reading before the window start.
        """
        metrics = ChannelMetrics(
            subscriber_count=channel.subscriber_count,
            is_subscriber_count_hidden=channel.is_subscriber_count_hidden,
            is_made_for_kids=channel.is_made_for_kids,
            uploads_read=uploads_read,
            is_playlist_truncated=is_playlist_truncated,
        )
        lives = [v for v in videos if self.is_live_stream(v, window)]
        games = [v for v in lives if self.is_game_stream(v, window)]
        metrics.live_stream_count = len(lives)
        metrics.game_stream_count = len(games)

        # shares are undefined without any live stream
        if lives:
            metrics.kana_title_share = sum(contain_kana(v.title) for v in lives) / len(lives)
            metrics.game_share = len(games) / len(lives)

        if games:
            metrics.game_stream_hours = sum((v.live_duration_minutes or 0.0) for v in games) / 60
            views = [v.view_count for v in games if v.view_count is not None]
            metrics.median_game_stream_views = statistics.median(views) if views else None
            metrics.last_game_stream_at = max(v.actual_start for v in games if v.actual_start is not None).isoformat()
            metrics.chat_replay_sample = self.sample_chat_replay_videos(games)
        return metrics

    def sample_chat_replay_videos(self, games: list[VideoSnapshot]) -> list[str]:
        """Picks the C5 sample: the game streams with the smallest hash(video_id + salt)."""
        size = self._policy.criteria.c5_sample_size
        ordered = sorted(games, key=lambda v: hash_salted(v.video_id, self._policy.hash_salt))
        return [v.video_id for v in ordered[:size]]
