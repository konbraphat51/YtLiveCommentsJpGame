"""Measures C5 for candidates still PENDING on it by reading the watch pages of their sampled game streams."""

from __future__ import annotations

from dataclasses import dataclass

from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Selection.EligibilityRejudger import EligibilityRejudger
from GameChatCollector.Sources.WatchPageScraper import WatchPageBlockedError, WatchPageScraper
from GameChatCollector.Storage.CatalogRepository import CatalogRepository


@dataclass(frozen=True)
class ChatCheckReport:
    """Summary of one check-chat run."""

    checked_channels: int
    pages_fetched: int
    is_blocked: bool


class ChatReplayChecker:
    """Fetches the C5 sample's watch pages, stores chat-replay and game-card shares, and re-judges the candidate."""

    def __init__(self, policy: ChannelPolicy, repository: CatalogRepository, scraper: WatchPageScraper, rejudger: EligibilityRejudger) -> None:
        """Creates the checker."""
        self._policy = policy
        self._repository = repository
        self._scraper = scraper
        self._rejudger = rejudger

    def check(self, reference_date: str, max_channels: int) -> ChatCheckReport:
        """Checks up to max_channels candidates that are PENDING on C5; stops at the first bot check."""
        records = [r for r in self._repository.iterate_eligibility(self._policy.policy_version, reference_date) if "C5" in r.pending_criteria]
        checked = fetched = 0
        for record in records[:max_channels]:
            metrics = ChannelMetrics.from_json_dict(record.metrics)
            available = game_cards = 0
            try:
                for video_id in metrics.chat_replay_sample:
                    facts = self._scraper.fetch_facts(video_id)
                    fetched += 1
                    available += facts.is_chat_replay_available
                    game_cards += facts.game_card_title is not None
            except WatchPageBlockedError:
                return ChatCheckReport(checked, fetched, is_blocked=True)
            size = len(metrics.chat_replay_sample)
            metrics.chat_replay_available = available
            metrics.chat_replay_share = available / size if size else 0.0
            metrics.game_card_share = game_cards / size if size else None
            self._rejudger.rejudge(record, metrics)
            checked += 1
        return ChatCheckReport(checked, fetched, is_blocked=False)
