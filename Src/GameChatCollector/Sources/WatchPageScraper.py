"""Reads chat-replay availability and the game card from a video's watch page (ytInitialData); parser to be verified in the Phase 0 spike."""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

INITIAL_DATA_PATTERN = re.compile(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", re.S)
WATCH_URL = "https://www.youtube.com/watch"


class WatchPageBlockedError(RuntimeError):
    """Raised when YouTube answers with its bot-check page; the caller must stop instead of retrying."""


@dataclass(frozen=True)
class WatchPageFacts:
    """What the policy needs from one watch page."""

    video_id: str
    is_chat_replay_available: bool
    game_card_title: str | None
    game_card_browse_id: str | None


def iterate_dicts(node: Any) -> Iterator[dict[str, Any]]:
    """Yields every dict nested in a JSON value (depth-first)."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from iterate_dicts(value)
    elif isinstance(node, list):
        for value in node:
            yield from iterate_dicts(value)


def parse_watch_facts(video_id: str, initial_data: dict[str, Any]) -> WatchPageFacts:
    """Extracts chat replay availability and the game card from ytInitialData.

    Args:
        video_id: The video the page belongs to.
        initial_data: The parsed ytInitialData object.
    """
    results = initial_data.get("contents", {}).get("twoColumnWatchNextResults", {})
    # an archive with chat replay carries a liveChatRenderer; a disabled replay shows a conversationBarRenderer message
    is_available = "liveChatRenderer" in results.get("conversationBar", {})
    title: str | None = None
    browse_id: str | None = None
    for node in iterate_dicts(results):
        renderer = node.get("richMetadataRenderer")
        if isinstance(renderer, dict) and renderer.get("style") == "RICH_METADATA_RENDERER_STYLE_BOX_ART":
            title = renderer.get("title", {}).get("simpleText") or "".join(run.get("text", "") for run in renderer.get("title", {}).get("runs", []))
            browse_id = renderer.get("endpoint", {}).get("browseEndpoint", {}).get("browseId")
            break
    return WatchPageFacts(video_id, is_available, title or None, browse_id)


class WatchPageScraper:
    """Fetches watch pages politely (one request per interval, with jitter) and parses them."""

    def __init__(self, http: httpx.Client | None = None, min_interval_seconds: float = 1.0) -> None:
        """Creates a scraper.

        Args:
            http: Optional HTTP client (for tests).
            min_interval_seconds: Minimum delay between requests.
        """
        self._http = http or httpx.Client(timeout=30.0, follow_redirects=False, headers={"Accept-Language": "ja,en;q=0.8", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"})
        self._min_interval = min_interval_seconds
        self._last_request = 0.0

    def fetch_facts(self, video_id: str) -> WatchPageFacts:
        """Fetches and parses one watch page; raises WatchPageBlockedError on a bot check."""
        wait = self._min_interval + random.uniform(0, self._min_interval / 2) - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        response = self._http.get(WATCH_URL, params={"v": video_id, "hl": "ja", "gl": "JP"})
        self._last_request = time.monotonic()
        if response.is_redirect or response.status_code == 429:
            raise WatchPageBlockedError(f"watch page blocked (HTTP {response.status_code}); run check-chat from another network")
        response.raise_for_status()
        match = INITIAL_DATA_PATTERN.search(response.text)
        if match is None:
            raise ValueError(f"ytInitialData not found for {video_id}")
        data: dict[str, Any] = json.loads(match.group(1))
        return parse_watch_facts(video_id, data)
