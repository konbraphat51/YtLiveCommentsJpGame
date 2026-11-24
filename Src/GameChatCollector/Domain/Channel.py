"""Domain records of channels and videos as observed through the YouTube Data API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


def parse_api_datetime(value: str | None) -> datetime | None:
    """Parses an RFC 3339 timestamp returned by the Data API, or returns None."""
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True)
class ChannelSnapshot:
    """A channel as returned by channels.list at one point in time."""

    channel_id: str
    title: str
    description: str
    custom_url: str | None
    country: str | None
    subscriber_count: int | None
    is_subscriber_count_hidden: bool
    video_count: int
    is_made_for_kids: bool

    @property
    def uploads_playlist_id(self) -> str:
        """The uploads playlist ID, derived from the channel ID without an API call."""
        return "UU" + self.channel_id[2:]

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> ChannelSnapshot:
        """Builds a snapshot from one channels.list item (parts snippet, statistics, status)."""
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        status = item.get("status", {})
        is_hidden = bool(statistics.get("hiddenSubscriberCount", False))
        raw_subscribers = statistics.get("subscriberCount")
        return cls(
            channel_id=item["id"],
            title=snippet.get("title", ""),
            description=snippet.get("description", ""),
            custom_url=snippet.get("customUrl"),
            country=snippet.get("country"),
            subscriber_count=None if is_hidden or raw_subscribers is None else int(raw_subscribers),
            is_subscriber_count_hidden=is_hidden,
            video_count=int(statistics.get("videoCount", 0)),
            is_made_for_kids=bool(status.get("madeForKids", False)),
        )


@dataclass(frozen=True)
class VideoSnapshot:
    """The fields of a videos.list item that the channel policy needs."""

    video_id: str
    channel_id: str
    title: str
    category_id: int | None
    published_at: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    view_count: int | None

    @property
    def live_duration_minutes(self) -> float | None:
        """Length of the completed live stream in minutes, or None if it was not a completed live stream."""
        if self.actual_start is None or self.actual_end is None:
            return None
        return (self.actual_end - self.actual_start).total_seconds() / 60

    @classmethod
    def from_api(cls, item: dict[str, Any]) -> VideoSnapshot:
        """Builds a snapshot from one videos.list item (parts snippet, liveStreamingDetails, statistics)."""
        snippet = item.get("snippet", {})
        live = item.get("liveStreamingDetails", {})
        statistics = item.get("statistics", {})
        category = snippet.get("categoryId")
        views = statistics.get("viewCount")
        return cls(
            video_id=item["id"],
            channel_id=snippet.get("channelId", ""),
            title=snippet.get("title", ""),
            category_id=int(category) if category is not None else None,
            published_at=parse_api_datetime(snippet.get("publishedAt")),
            actual_start=parse_api_datetime(live.get("actualStartTime")),
            actual_end=parse_api_datetime(live.get("actualEndTime")),
            view_count=int(views) if views is not None else None,
        )


@dataclass(frozen=True)
class ChannelCandidate:
    """A channel found by one or more candidate sources, with the titles it was found through."""

    channel_id: str
    discovery_source: str
    evidence_titles: tuple[str, ...] = ()
