"""SQLite catalog for channel selection: candidates, discoveries, eligibility, search points and quota usage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from GameChatCollector.Operations.QuotaSettings import Lane

SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_candidates (
  channel_id TEXT PRIMARY KEY,
  primary_source TEXT NOT NULL,
  first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidate_discoveries (
  channel_id TEXT NOT NULL,
  source TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  evidence_title TEXT NOT NULL,
  discovered_at TEXT NOT NULL,
  PRIMARY KEY (channel_id, source, evidence_id)
);
CREATE TABLE IF NOT EXISTS channel_eligibility (
  channel_id TEXT NOT NULL,
  policy_version TEXT NOT NULL,
  reference_date TEXT NOT NULL,
  evaluated_at TEXT NOT NULL,
  stage TEXT NOT NULL,
  status TEXT NOT NULL,
  failed_criteria TEXT NOT NULL,
  pending_criteria TEXT NOT NULL,
  criteria_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  channel_json TEXT NOT NULL,
  manual_exclusion_reason TEXT,
  PRIMARY KEY (channel_id, policy_version, reference_date)
);
CREATE TABLE IF NOT EXISTS search_points (
  policy_version TEXT NOT NULL,
  reference_date TEXT NOT NULL,
  point_index INTEGER NOT NULL,
  query_term TEXT NOT NULL,
  published_after TEXT NOT NULL,
  published_before TEXT NOT NULL,
  times_searched INTEGER NOT NULL DEFAULT 0,
  last_result_count INTEGER,
  last_searched_at TEXT,
  PRIMARY KEY (policy_version, reference_date, point_index)
);
CREATE TABLE IF NOT EXISTS quota_usage (
  pt_date TEXT NOT NULL,
  lane TEXT NOT NULL,
  units INTEGER NOT NULL,
  PRIMARY KEY (pt_date, lane)
);
"""


@dataclass(frozen=True)
class EligibilityRecord:
    """One row of channel_eligibility."""

    channel_id: str
    policy_version: str
    reference_date: str
    evaluated_at: str
    stage: str
    status: str
    failed_criteria: list[str]
    pending_criteria: list[str]
    criteria: dict[str, Any]
    metrics: dict[str, Any]
    channel: dict[str, Any]
    manual_exclusion_reason: str | None = None


@dataclass(frozen=True)
class CandidateRecord:
    """A candidate with its sources and evidence titles."""

    channel_id: str
    primary_source: str
    sources: list[str]
    evidence_titles: list[str]


class CatalogRepository:
    """All SQL for channel selection lives here; it also implements the QuotaLedger protocol."""

    def __init__(self, path: Path) -> None:
        """Opens (and creates if needed) the catalog."""
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)

    def close(self) -> None:
        """Closes the connection."""
        self._connection.close()

    # --- quota ledger ---

    def load_usage(self, quota_day: date) -> dict[Lane, int]:
        """Returns units spent per lane on the Pacific-time quota day."""
        rows = self._connection.execute("SELECT lane, units FROM quota_usage WHERE pt_date = ?", (quota_day.isoformat(),))
        return {Lane(row["lane"]): int(row["units"]) for row in rows}

    def record_usage(self, quota_day: date, lane: Lane, units: int) -> None:
        """Adds spent units."""
        with self._connection:
            self._connection.execute(
                "INSERT INTO quota_usage (pt_date, lane, units) VALUES (?, ?, ?) ON CONFLICT (pt_date, lane) DO UPDATE SET units = units + excluded.units",
                (quota_day.isoformat(), lane.value, units),
            )

    # --- candidates ---

    def add_discovery(self, channel_id: str, source: str, evidence_id: str, evidence_title: str, discovered_at: datetime) -> bool:
        """Records that a source found a channel; returns True if the channel is a new candidate."""
        with self._connection:
            cursor = self._connection.execute("INSERT OR IGNORE INTO channel_candidates (channel_id, primary_source, first_seen_at) VALUES (?, ?, ?)", (channel_id, source, discovered_at.isoformat()))
            self._connection.execute(
                "INSERT OR IGNORE INTO candidate_discoveries (channel_id, source, evidence_id, evidence_title, discovered_at) VALUES (?, ?, ?, ?, ?)",
                (channel_id, source, evidence_id, evidence_title, discovered_at.isoformat()),
            )
        return cursor.rowcount == 1

    def list_candidates(self) -> list[CandidateRecord]:
        """Returns every candidate with its sources and evidence titles."""
        candidates = {row["channel_id"]: CandidateRecord(row["channel_id"], row["primary_source"], [], []) for row in self._connection.execute("SELECT * FROM channel_candidates")}
        for row in self._connection.execute("SELECT channel_id, source, evidence_title FROM candidate_discoveries"):
            record = candidates[row["channel_id"]]
            if row["source"] not in record.sources:
                record.sources.append(row["source"])
            record.evidence_titles.append(row["evidence_title"])
        return list(candidates.values())

    # --- eligibility ---

    def save_eligibility(self, record: EligibilityRecord) -> None:
        """Inserts or replaces the evaluation of one candidate for one policy version and reference date."""
        with self._connection:
            self._connection.execute(
                "INSERT OR REPLACE INTO channel_eligibility VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.channel_id,
                    record.policy_version,
                    record.reference_date,
                    record.evaluated_at,
                    record.stage,
                    record.status,
                    json.dumps(record.failed_criteria),
                    json.dumps(record.pending_criteria),
                    json.dumps(record.criteria, ensure_ascii=False),
                    json.dumps(record.metrics, ensure_ascii=False),
                    json.dumps(record.channel, ensure_ascii=False),
                    record.manual_exclusion_reason,
                ),
            )

    def iterate_eligibility(self, policy_version: str, reference_date: str) -> Iterator[EligibilityRecord]:
        """Yields every evaluation of the given policy version and reference date."""
        rows = self._connection.execute("SELECT * FROM channel_eligibility WHERE policy_version = ? AND reference_date = ? ORDER BY channel_id", (policy_version, reference_date))
        for row in rows:
            yield EligibilityRecord(
                channel_id=row["channel_id"],
                policy_version=row["policy_version"],
                reference_date=row["reference_date"],
                evaluated_at=row["evaluated_at"],
                stage=row["stage"],
                status=row["status"],
                failed_criteria=json.loads(row["failed_criteria"]),
                pending_criteria=json.loads(row["pending_criteria"]),
                criteria=json.loads(row["criteria_json"]),
                metrics=json.loads(row["metrics_json"]),
                channel=json.loads(row["channel_json"]),
                manual_exclusion_reason=row["manual_exclusion_reason"],
            )

    def list_evaluated_channel_ids(self, policy_version: str, reference_date: str) -> set[str]:
        """Returns the IDs already evaluated for this policy version and reference date."""
        rows = self._connection.execute("SELECT channel_id FROM channel_eligibility WHERE policy_version = ? AND reference_date = ?", (policy_version, reference_date))
        return {row["channel_id"] for row in rows}

    # --- search points ---

    def upsert_search_point(self, policy_version: str, reference_date: str, point_index: int, query_term: str, published_after: datetime, published_before: datetime) -> None:
        """Registers a search point if it does not exist yet."""
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO search_points (policy_version, reference_date, point_index, query_term, published_after, published_before) VALUES (?, ?, ?, ?, ?, ?)",
                (policy_version, reference_date, point_index, query_term, published_after.isoformat(), published_before.isoformat()),
            )

    def load_search_counts(self, policy_version: str, reference_date: str) -> dict[int, int]:
        """Returns times_searched per point index."""
        rows = self._connection.execute("SELECT point_index, times_searched FROM search_points WHERE policy_version = ? AND reference_date = ?", (policy_version, reference_date))
        return {int(row["point_index"]): int(row["times_searched"]) for row in rows}

    def mark_searched(self, policy_version: str, reference_date: str, point_index: int, result_count: int, searched_at: datetime) -> None:
        """Increments times_searched and stores the result count."""
        with self._connection:
            self._connection.execute(
                "UPDATE search_points SET times_searched = times_searched + 1, last_result_count = ?, last_searched_at = ? WHERE policy_version = ? AND reference_date = ? AND point_index = ?",
                (result_count, searched_at.isoformat(), policy_version, reference_date, point_index),
            )
