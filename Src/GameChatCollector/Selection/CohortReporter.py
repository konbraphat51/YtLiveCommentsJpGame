"""Writes the evaluated channel list, the provisional cohort and a Markdown summary with sensitivity analysis."""

from __future__ import annotations

import csv
import statistics
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy, CriteriaThresholds
from GameChatCollector.Selection.EligibilityCriteria import CriterionOutcome, EligibilityCriterion, build_default_criteria
from GameChatCollector.Storage.CatalogRepository import CandidateRecord, EligibilityRecord

LIST_FIELDS = [
    "channel_id",
    "title",
    "handle",
    "status",
    "stage",
    "failed_criteria",
    "pending_criteria",
    "subscriber_count",
    "live_stream_count",
    "game_stream_count",
    "kana_title_share",
    "game_share",
    "game_stream_hours",
    "median_game_stream_views",
    "last_game_stream_at",
    "c6_flags",
    "sources",
]

# One-at-a-time alternatives for the sensitivity table (the policy value is added automatically).
SENSITIVITY_GRID: dict[str, list[float]] = {
    "c1_min_kana_title_share": [0.5, 0.7, 0.8, 0.9, 1.0],
    "c2_min_game_streams": [4, 6, 8, 12, 16, 24],
    "c3_min_game_share": [0.1, 0.2, 0.3, 0.5, 0.7],
    "c4_min_subscribers": [5000, 10000, 20000, 50000, 100000],
}


@dataclass(frozen=True)
class CohortFiles:
    """Paths written by the reporter."""

    eligibility_csv: Path
    cohort_csv: Path
    summary_md: Path


class CohortReporter:
    """Turns channel_eligibility rows into files people can review."""

    def __init__(self, policy: ChannelPolicy, criteria: list[EligibilityCriterion] | None = None) -> None:
        """Creates a reporter for one policy."""
        self._policy = policy
        self._criteria = criteria or build_default_criteria()

    def write(self, records: list[EligibilityRecord], candidates: list[CandidateRecord], directory: Path) -> CohortFiles:
        """Writes ChannelEligibility.csv (every candidate), Cohort.csv (PASSED and PENDING) and Summary.md."""
        directory.mkdir(parents=True, exist_ok=True)
        sources = {c.channel_id: c.sources for c in candidates}
        rows = [self._build_row(r, sources.get(r.channel_id, [])) for r in records]
        rows.sort(key=lambda row: (row["status"] != "PASSED", row["status"] != "PENDING", -(row["subscriber_count"] or 0)))
        files = CohortFiles(directory / "ChannelEligibility.csv", directory / "Cohort.csv", directory / "Summary.md")
        self._write_csv(files.eligibility_csv, rows)
        self._write_csv(files.cohort_csv, [row for row in rows if row["status"] in ("PASSED", "PENDING")])
        files.summary_md.write_text(self.build_summary(records, candidates), encoding="utf-8")
        return files

    def _build_row(self, record: EligibilityRecord, sources: list[str]) -> dict[str, Any]:
        """Flattens one record."""
        metrics, channel = record.metrics, record.channel
        c6 = record.criteria.get("C6", {})
        return {
            "channel_id": record.channel_id,
            "title": channel.get("title", ""),
            "handle": channel.get("custom_url") or "",
            "status": record.status,
            "stage": record.stage,
            "failed_criteria": ";".join(record.failed_criteria),
            "pending_criteria": ";".join(record.pending_criteria),
            "subscriber_count": metrics.get("subscriber_count"),
            "live_stream_count": metrics.get("live_stream_count") if record.stage == "MEASURED" else None,
            "game_stream_count": metrics.get("game_stream_count") if record.stage == "MEASURED" else None,
            "kana_title_share": _round(metrics.get("kana_title_share")),
            "game_share": _round(metrics.get("game_share")),
            "game_stream_hours": _round(metrics.get("game_stream_hours")) if record.stage == "MEASURED" else None,
            "median_game_stream_views": metrics.get("median_game_stream_views"),
            "last_game_stream_at": metrics.get("last_game_stream_at"),
            "c6_flags": c6.get("value") or "",
            "sources": ";".join(sources),
        }

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
        """Writes rows with a BOM so the file opens correctly in Excel on Windows."""
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=LIST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def count_passing(self, measured: list[ChannelMetrics], c6_failed: list[bool], thresholds: CriteriaThresholds) -> int:
        """Counts measured channels that pass C1-C4 and are not C6 failures under alternative thresholds."""
        policy = self._policy.model_copy(update={"criteria": thresholds})
        checks = [c for c in self._criteria if c.criterion_id in ("C1", "C2", "C3", "C4")]
        return sum(1 for metrics, is_c6_failed in zip(measured, c6_failed, strict=True) if not is_c6_failed and all(c.check(metrics, policy).outcome is CriterionOutcome.PASS for c in checks))

    def build_summary(self, records: list[EligibilityRecord], candidates: list[CandidateRecord]) -> str:
        """Builds the Markdown summary: counts, failure reasons, distributions and sensitivity."""
        policy = self._policy
        measured_records = [r for r in records if r.stage == "MEASURED"]
        measured = [ChannelMetrics.from_json_dict(r.metrics) for r in measured_records]
        c6_failed = ["C6" in r.failed_criteria for r in measured_records]
        lines = [
            f"# Channel Eligibility Summary (policy {policy.policy_version}, reference {records[0].reference_date if records else '-'})",
            "",
            "Generated by `collector channels report`. C5 (chat replay) is PENDING until `collector channels check-chat` runs where watch pages are reachable.",
            "",
            "## Counts",
            "",
            "| Item | Count |",
            "| --- | --- |",
            f"| Candidates found | {len(candidates)} |",
            f"| Evaluated | {len(records)} |",
        ]
        lines += [f"| Stage {stage} | {count} |" for stage, count in sorted(Counter(r.stage for r in records).items())]
        lines += [f"| Status {status} | {count} |" for status, count in sorted(Counter(r.status for r in records).items())]
        source_counts = Counter(source for c in candidates for source in c.sources)
        lines += [f"| Source {source} | {count} |" for source, count in sorted(source_counts.items())]

        lines += ["", "## Failed criteria (a candidate can fail several)", "", "| Criterion | Screened | Measured |", "| --- | --- | --- |"]
        screened_fails = Counter(c for r in records if r.stage == "SCREENED" for c in r.failed_criteria)
        measured_fails = Counter(c for r in measured_records for c in r.failed_criteria)
        for criterion in ["C1", "C2", "C3", "C4", "C5", "C6", "NOT_FOUND"]:
            lines.append(f"| {criterion} | {screened_fails.get(criterion, 0)} | {measured_fails.get(criterion, 0)} |")

        lines += ["", f"## Distributions over measured candidates (n = {len(measured)})", "", "| Metric | p10 | p25 | median | p75 | p90 |", "| --- | --- | --- | --- | --- | --- |"]
        for name in ["kana_title_share", "live_stream_count", "game_stream_count", "game_share", "subscriber_count", "game_stream_hours"]:
            values = [float(v) for m in measured if (v := getattr(m, name)) is not None]
            lines.append(f"| {name} | " + " | ".join(_format_number(q) for q in _quantiles(values)) + " |")

        lines += ["", "## Sensitivity (C1-C4 and C6 not failed; one threshold varied at a time)", "", "| Threshold | Value | Channels passing |", "| --- | --- | --- |"]
        base = policy.criteria
        for field, values in SENSITIVITY_GRID.items():
            for value in sorted(set(values) | {float(getattr(base, field))}):
                typed_value = int(value) if field in ("c2_min_game_streams", "c4_min_subscribers") else value
                thresholds = base.model_copy(update={field: typed_value})
                marker = " (policy)" if value == getattr(base, field) else ""
                lines.append(f"| {field} | {_format_number(value)}{marker} | {self.count_passing(measured, c6_failed, thresholds)} |")
        lines += ["", "## C6 review queue (decide with Docs/ChannelTypeChecklist.md)", "", "| channel_id | Title | Flags |", "| --- | --- | --- |"]
        for record in records:
            if "C6" in record.pending_criteria:
                lines.append(f"| {record.channel_id} | {record.channel.get('title', '')} | {record.criteria.get('C6', {}).get('value') or ''} |")
        lines.append("")
        return "\n".join(lines)


def _round(value: Any) -> Any:
    """Rounds floats to 3 decimals for display."""
    return round(value, 3) if isinstance(value, float) else value


def _quantiles(values: list[float]) -> list[float | None]:
    """Returns p10, p25, p50, p75, p90 (None when there are fewer than two values)."""
    if len(values) < 2:
        return [None] * 5
    deciles = statistics.quantiles(values, n=20, method="inclusive")
    return [deciles[1], deciles[4], statistics.median(values), deciles[14], deciles[17]]


def _format_number(value: float | None) -> str:
    """Formats a number compactly."""
    if value is None:
        return "-"
    return f"{value:.0f}" if value >= 10 or value == int(value) else f"{value:.2f}"
