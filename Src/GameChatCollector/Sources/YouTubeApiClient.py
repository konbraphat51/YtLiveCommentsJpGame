"""Thin YouTube Data API v3 client that charges every call to a quota lane and stores every response raw."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from GameChatCollector.Domain.Channel import parse_api_datetime
from GameChatCollector.Operations.QuotaBudget import QuotaBudget, QuotaExhaustedError
from GameChatCollector.Operations.QuotaSettings import Lane, QuotaSettings
from GameChatCollector.Storage.RawStore import RawStore

API_ROOT = "https://www.googleapis.com/youtube/v3/"
BATCH_SIZE = 50


@dataclass(frozen=True)
class PlaylistReadResult:
    """Playlist items read back to a cut-off date."""

    items: list[dict[str, Any]]
    is_truncated: bool


class YouTubeApiClient:
    """Calls the Data API; the budget is charged before each call so the lane limit is never exceeded."""

    def __init__(self, api_key: str, budget: QuotaBudget, quota_settings: QuotaSettings, raw_store: RawStore, http: httpx.Client | None = None, clock: Callable[[], datetime] | None = None) -> None:
        """Creates a client.

        Args:
            api_key: Data API key, sent in the X-Goog-Api-Key header.
            budget: Quota budget charged per call.
            quota_settings: Source of per-method costs.
            raw_store: Where responses are archived.
            http: Optional HTTP client (for tests).
            clock: Optional clock returning an aware datetime (for tests).
        """
        self._budget = budget
        self._quota_settings = quota_settings
        self._raw_store = raw_store
        self._http = http or httpx.Client(base_url=API_ROOT, timeout=30.0, headers={"X-Goog-Api-Key": api_key})
        self._clock = clock or (lambda: datetime.now(UTC))

    def _call(self, method: str, lane: Lane, params: dict[str, Any]) -> dict[str, Any]:
        """Charges the lane, performs the call, archives the response and returns it."""
        now = self._clock()
        self._budget.spend(lane, self._quota_settings.cost(method), now)
        response = self._http.get(method.split(".")[0], params=params)
        payload: dict[str, Any] = response.json()
        self._raw_store.put_json(f"Api/{method}", payload, {"params": params, "status": response.status_code}, now)
        if response.status_code == 403 and "quotaExceeded" in response.text:
            raise QuotaExhaustedError("Data API reported quotaExceeded")
        if response.status_code == 404:
            return {"items": []}
        response.raise_for_status()
        return payload

    def search_completed_game_videos(self, published_after: datetime, published_before: datetime, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Runs one search.list call over [published_after, published_before) and returns its items (lane L4).

        Args:
            published_after: Lower bound of publishedAt.
            published_before: Upper bound of publishedAt.
            params: Fixed frame parameters (category, region, language, order, maxResults).
        """
        query = {"part": "snippet", "type": "video", "eventType": "completed", **params, "publishedAfter": _format(published_after), "publishedBefore": _format(published_before)}
        items: list[dict[str, Any]] = self._call("search.list", Lane.L4_DISCOVERY, query).get("items", [])
        return items

    def list_channels(self, channel_ids: list[str], lane: Lane) -> list[dict[str, Any]]:
        """Fetches channels 50 at a time (parts snippet, statistics, status)."""
        items: list[dict[str, Any]] = []
        for start in range(0, len(channel_ids), BATCH_SIZE):
            chunk = channel_ids[start : start + BATCH_SIZE]
            items += self._call("channels.list", lane, {"part": "snippet,statistics,status", "id": ",".join(chunk), "maxResults": BATCH_SIZE}).get("items", [])
        return items

    def read_playlist_since(self, playlist_id: str, since: datetime, max_pages: int, lane: Lane) -> PlaylistReadResult:
        """Reads playlist items newest first until an item older than `since` appears or the page limit is hit."""
        items: list[dict[str, Any]] = []
        token: str | None = None
        for _ in range(max_pages):
            params: dict[str, Any] = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": BATCH_SIZE}
            if token:
                params["pageToken"] = token
            page = self._call("playlistItems.list", lane, params)
            page_items: list[dict[str, Any]] = page.get("items", [])
            items += page_items
            published = [parse_api_datetime(i.get("contentDetails", {}).get("videoPublishedAt")) for i in page_items]
            token = page.get("nextPageToken")
            if not token or any(p is not None and p < since for p in published):
                return PlaylistReadResult(items, is_truncated=False)
        return PlaylistReadResult(items, is_truncated=True)

    def list_videos(self, video_ids: list[str], lane: Lane) -> list[dict[str, Any]]:
        """Fetches videos 50 at a time (parts snippet, liveStreamingDetails, statistics)."""
        items: list[dict[str, Any]] = []
        for start in range(0, len(video_ids), BATCH_SIZE):
            chunk = video_ids[start : start + BATCH_SIZE]
            items += self._call("videos.list", lane, {"part": "snippet,liveStreamingDetails,statistics", "id": ",".join(chunk), "maxResults": BATCH_SIZE}).get("items", [])
        return items


def _format(moment: datetime) -> str:
    """Formats an aware datetime as the RFC 3339 string the API expects."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
