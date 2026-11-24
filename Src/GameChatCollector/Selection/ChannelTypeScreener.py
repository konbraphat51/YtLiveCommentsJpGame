"""Judges criterion C6 (channel type) from automatic flags plus logged human review decisions."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from GameChatCollector.Domain.Channel import ChannelSnapshot
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Selection.EligibilityCriteria import CriterionOutcome, CriterionResult


@dataclass(frozen=True)
class ChannelTypeReview:
    """A logged human decision on C6 for one channel."""

    channel_id: str
    decision: CriterionOutcome
    reason: str
    reviewer: str
    reviewed_at: str


class ChannelTypeReviewBook:
    """Reads the C6 review log (Config/ChannelTypeReviews.csv)."""

    FIELDS = ("channel_id", "decision", "reason", "reviewer", "reviewed_at")

    def __init__(self, reviews: dict[str, ChannelTypeReview]) -> None:
        """Creates a book from reviews keyed by channel ID."""
        self._reviews = reviews

    @classmethod
    def load(cls, path: Path) -> ChannelTypeReviewBook:
        """Loads the CSV; a missing file means no reviews."""
        if not path.exists():
            return cls({})
        with path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        reviews = {row["channel_id"]: ChannelTypeReview(row["channel_id"], CriterionOutcome(row["decision"]), row["reason"], row["reviewer"], row["reviewed_at"]) for row in rows}
        return cls(reviews)

    def find(self, channel_id: str) -> ChannelTypeReview | None:
        """Returns the review of the channel, if any."""
        return self._reviews.get(channel_id)


class ChannelTypeScreener:
    """C6: madeForKids fails automatically; keyword hits in the title need a human decision."""

    criterion_id = "C6"

    def __init__(self, policy: ChannelPolicy, review_book: ChannelTypeReviewBook) -> None:
        """Creates a screener.

        Args:
            policy: The policy holding the keyword lists.
            review_book: Logged human decisions.
        """
        self._policy = policy
        self._review_book = review_book

    def find_flags(self, channel: ChannelSnapshot) -> list[str]:
        """Returns the automatic flags raised for the channel."""
        flags: list[str] = []
        if channel.is_made_for_kids:
            flags.append("made_for_kids")
        # only the title and handle are checked; descriptions mention clips and "official" too often
        surface = f"{channel.title} {channel.custom_url or ''}".casefold()
        flags += [f"clip:{k}" for k in self._policy.channel_type.clip_keywords if k.casefold() in surface]
        flags += [f"official:{k}" for k in self._policy.channel_type.official_keywords if k.casefold() in surface]
        return flags

    def check(self, channel: ChannelSnapshot) -> CriterionResult:
        """Judges C6: a review decision wins; madeForKids fails; other flags stay PENDING; no flag passes."""
        flags = self.find_flags(channel)
        value = ";".join(flags) if flags else None
        review = self._review_book.find(channel.channel_id)
        if review is not None:
            return CriterionResult(self.criterion_id, review.decision, value)
        if channel.is_made_for_kids:
            return CriterionResult(self.criterion_id, CriterionOutcome.FAIL, value)
        if flags:
            return CriterionResult(self.criterion_id, CriterionOutcome.PENDING, value)
        return CriterionResult(self.criterion_id, CriterionOutcome.PASS, value)
