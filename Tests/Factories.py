"""Builders of domain objects and policies for unit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from GameChatCollector.Domain.Channel import ChannelSnapshot, VideoSnapshot
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy

POLICY_PATH = Path(__file__).resolve().parents[1] / "Config" / "ChannelPolicy.yaml"


def load_policy() -> ChannelPolicy:
    """Loads the repository's channel policy."""
    return ChannelPolicy.load(POLICY_PATH)


def build_channel(channel_id: str = "UCxxxxxxxxxxxxxxxxxxxxxx", title: str = "テストch", subscribers: int | None = 20000, is_made_for_kids: bool = False) -> ChannelSnapshot:
    """Builds a channel snapshot."""
    return ChannelSnapshot(channel_id, title, "", None, "JP", subscribers, subscribers is None, 100, is_made_for_kids)


def build_live(video_id: str, start: datetime, minutes: int = 120, category_id: int = 20, title: str = "【マイクラ】雑談しながら", views: int = 1000) -> VideoSnapshot:
    """Builds a completed live stream snapshot."""
    return VideoSnapshot(video_id, "UCxxxxxxxxxxxxxxxxxxxxxx", title, category_id, start, start, start + timedelta(minutes=minutes), views)


REFERENCE = datetime(2026, 11, 24, tzinfo=UTC)
