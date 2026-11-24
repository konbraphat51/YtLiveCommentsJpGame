"""Candidate discovery: the search.list frame (time points x query terms) and curated CSV lists."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from GameChatCollector.Domain.Channel import ChannelCandidate
from GameChatCollector.Selection.ChannelPolicy import SearchFrameSettings


def compute_van_der_corput(index: int, base: int = 2) -> float:
    """Returns the index-th element of the van der Corput sequence in [0, 1); any prefix is evenly spread."""
    value, denominator = 0.0, 1.0
    while index > 0:
        index, digit = divmod(index, base)
        denominator *= base
        value += digit / denominator
    return value


@dataclass(frozen=True)
class SearchPoint:
    """One search.list call of the frame: [published_after, published_before) with a query term."""

    point_index: int
    query_term: str
    published_after: datetime
    published_before: datetime


class SearchPointPlan:
    """Deterministic sequence of search points; any prefix covers the frame's days, hours and terms evenly."""

    def __init__(self, settings: SearchFrameSettings, reference_date: date) -> None:
        """Creates the plan for one reference date.

        Args:
            settings: Search frame settings of the policy.
            reference_date: The frame ends at 00:00 UTC of this date.
        """
        self._settings = settings
        self._frame_end = datetime.combine(reference_date, time.min, tzinfo=UTC)

    def build_point(self, index: int) -> SearchPoint:
        """Returns point i: day = floor(vdc(i+1) * frame_days), hour = (i * hour_step) mod 24, term = terms[i mod n]."""
        settings = self._settings
        day = int(compute_van_der_corput(index + 1) * settings.frame_days)
        hour = (index * settings.hour_step) % 24
        before = self._frame_end - timedelta(days=settings.frame_days) + timedelta(days=day, hours=hour)
        before = min(before, self._frame_end)
        term = settings.query_terms[index % len(settings.query_terms)]
        return SearchPoint(index, term, before - timedelta(hours=settings.lookback_hours), before)

    def build_points(self, count: int) -> list[SearchPoint]:
        """Returns the first `count` points."""
        return [self.build_point(i) for i in range(count)]

    def build_request_params(self, point: SearchPoint) -> dict[str, Any]:
        """Returns the fixed search.list parameters for the point (order=date, newest first)."""
        params: dict[str, Any] = {
            "order": "date",
            "maxResults": self._settings.max_results,
            "regionCode": self._settings.region_code,
            "relevanceLanguage": self._settings.relevance_language,
            "videoCategoryId": self._settings.video_category_id,
        }
        if point.query_term:
            params["q"] = point.query_term
        return params


class CsvCandidateSource:
    """Curated candidate list (Config/ChannelCandidates.csv: channel_id, source_label, note)."""

    def __init__(self, path: Path) -> None:
        """Creates a source reading the CSV at path."""
        self._path = path

    def discover(self) -> list[ChannelCandidate]:
        """Returns the candidates listed in the CSV; source names are prefixed with csv:."""
        if not self._path.exists():
            return []
        with self._path.open(encoding="utf-8", newline="") as file:
            return [ChannelCandidate(row["channel_id"], f"csv:{row['source_label']}", (row.get("note") or "",)) for row in csv.DictReader(file)]


SEARCH_SOURCE = "search"
