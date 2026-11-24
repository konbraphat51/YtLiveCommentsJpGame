"""Runs the search.list frame within the L4 budget and records every channel it finds."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from GameChatCollector.Operations.PriorityRules import DiscoveryItem, DiscoveryPriorityRule
from GameChatCollector.Operations.QuotaBudget import QuotaExhaustedError
from GameChatCollector.Selection.CandidateSources import SEARCH_SOURCE, SearchPointPlan
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Sources.YouTubeApiClient import YouTubeApiClient
from GameChatCollector.Storage.CatalogRepository import CatalogRepository


@dataclass(frozen=True)
class DiscoveryReport:
    """Summary of one discovery run."""

    points_searched: int
    videos_seen: int
    new_candidates: int
    is_budget_exhausted: bool


class ApiSearchCandidateSource:
    """Searches the frame's points in DiscoveryPriorityRule order until the point limit or the L4 budget is reached."""

    def __init__(self, policy: ChannelPolicy, client: YouTubeApiClient, repository: CatalogRepository, rule: DiscoveryPriorityRule, clock: Callable[[], datetime] | None = None) -> None:
        """Creates the source.

        Args:
            policy: Channel policy (search frame settings and version).
            client: Data API client.
            repository: Catalog for points and discoveries.
            rule: L4 priority rule.
            clock: Optional clock (for tests).
        """
        self._policy = policy
        self._client = client
        self._repository = repository
        self._rule = rule
        self._clock = clock or (lambda: datetime.now(UTC))

    def discover(self, reference_date: date, point_count: int, max_calls: int) -> DiscoveryReport:
        """Registers the first point_count points and searches up to max_calls of them.

        Args:
            reference_date: Reference date of the frame.
            point_count: Size of the point plan.
            max_calls: Upper bound on search.list calls in this run.
        """
        version, ref = self._policy.policy_version, reference_date.isoformat()
        plan = SearchPointPlan(self._policy.search_frame, reference_date)
        points = {p.point_index: p for p in plan.build_points(point_count)}
        for p in points.values():
            self._repository.upsert_search_point(version, ref, p.point_index, p.query_term, p.published_after, p.published_before)
        counts = self._repository.load_search_counts(version, ref)
        queue = self._rule.order([DiscoveryItem(i, counts.get(i, 0)) for i in points], self._clock())

        searched = seen = new = 0
        for item in queue[:max_calls]:
            point = points[item.point_index]
            try:
                results = self._client.search_completed_game_videos(point.published_after, point.published_before, plan.build_request_params(point))
            except QuotaExhaustedError:
                return DiscoveryReport(searched, seen, new, is_budget_exhausted=True)
            now = self._clock()
            for result in results:
                snippet = result.get("snippet", {})
                video_id = result.get("id", {}).get("videoId", "")
                new += self._repository.add_discovery(snippet.get("channelId", ""), SEARCH_SOURCE, video_id, snippet.get("title", ""), now)
            self._repository.mark_searched(version, ref, point.point_index, len(results), now)
            searched += 1
            seen += len(results)
        return DiscoveryReport(searched, seen, new, is_budget_exhausted=False)
