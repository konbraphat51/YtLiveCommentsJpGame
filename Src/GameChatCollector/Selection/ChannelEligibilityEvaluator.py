"""Measures candidates through the Data API (lane L3) and records their C1-C6 outcomes in channel_eligibility."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from GameChatCollector.Domain.Channel import ChannelSnapshot, VideoSnapshot, parse_api_datetime
from GameChatCollector.Operations.PriorityRules import EligibilityItem, EligibilityPriorityRule, EligibilityTier
from GameChatCollector.Operations.QuotaBudget import QuotaExhaustedError
from GameChatCollector.Operations.QuotaSettings import Lane
from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics, ChannelMetricsCalculator, ObservationWindow, contain_kana
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Selection.ChannelTypeScreener import ChannelTypeScreener
from GameChatCollector.Selection.EligibilityCriteria import CriterionOutcome, CriterionResult, EligibilityCriterion
from GameChatCollector.Sources.YouTubeApiClient import YouTubeApiClient
from GameChatCollector.Storage.CatalogRepository import CandidateRecord, CatalogRepository, EligibilityRecord


class EvaluationStage:
    """How far a candidate was measured."""

    # channel no longer exists
    NOT_FOUND = "NOT_FOUND"
    # stopped after channels.list by a screening rule
    SCREENED = "SCREENED"
    # uploads in the window were measured
    MEASURED = "MEASURED"


class EligibilityStatus:
    """Overall result."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    PENDING = "PENDING"


def summarize_outcomes(results: list[CriterionResult]) -> tuple[str, list[str], list[str]]:
    """Returns (status, failed IDs, pending IDs): any FAIL fails, else any PENDING is pending, else passed."""
    failed = [r.criterion_id for r in results if r.outcome is CriterionOutcome.FAIL]
    pending = [r.criterion_id for r in results if r.outcome is CriterionOutcome.PENDING]
    status = EligibilityStatus.FAILED if failed else EligibilityStatus.PENDING if pending else EligibilityStatus.PASSED
    return status, failed, pending


@dataclass(frozen=True)
class EvaluationReport:
    """Summary of one evaluation run."""

    evaluated: int
    counts_by_status: dict[str, int]
    is_budget_exhausted: bool


class ChannelEligibilityEvaluator:
    """Screens candidates cheaply with channels.list, then measures the rest from their uploads playlist."""

    def __init__(
        self,
        policy: ChannelPolicy,
        client: YouTubeApiClient,
        repository: CatalogRepository,
        criteria: list[EligibilityCriterion],
        screener: ChannelTypeScreener,
        rule: EligibilityPriorityRule,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Creates the evaluator.

        Args:
            policy: The channel policy.
            client: Data API client.
            repository: Catalog.
            criteria: Metric-based criteria (C1-C5).
            screener: C6 judge.
            rule: L3 priority rule.
            clock: Optional clock (for tests).
        """
        self._policy = policy
        self._client = client
        self._repository = repository
        self._criteria = criteria
        self._screener = screener
        self._rule = rule
        self._calculator = ChannelMetricsCalculator(policy)
        self._clock = clock or (lambda: datetime.now(UTC))

    def evaluate_pending_candidates(self, reference_date: date, max_candidates: int, batch_size: int = 50) -> EvaluationReport:
        """Evaluates not-yet-evaluated candidates in L3 priority order until the limit or the budget runs out."""
        version, ref = self._policy.policy_version, reference_date.isoformat()
        done = self._repository.list_evaluated_channel_ids(version, ref)
        candidates = {c.channel_id: c for c in self._repository.list_candidates() if c.channel_id not in done}
        items = [EligibilityItem(c.channel_id, EligibilityTier.NEW_CANDIDATE, c.primary_source) for c in candidates.values()]
        queue = [candidates[i.channel_id] for i in self._rule.order(items, self._clock())][:max_candidates]

        counts: dict[str, int] = {}
        evaluated = 0
        try:
            for start in range(0, len(queue), batch_size):
                for record in self._evaluate_batch(queue[start : start + batch_size], reference_date):
                    counts[record.status] = counts.get(record.status, 0) + 1
                    evaluated += 1
        except QuotaExhaustedError:
            return EvaluationReport(evaluated, counts, is_budget_exhausted=True)
        return EvaluationReport(evaluated, counts, is_budget_exhausted=False)

    def _evaluate_batch(self, batch: list[CandidateRecord], reference_date: date) -> list[EligibilityRecord]:
        """Evaluates up to 50 candidates; each record is saved as soon as it is complete."""
        items = self._client.list_channels([c.channel_id for c in batch], Lane.L3_ELIGIBILITY)
        snapshots = {item["id"]: ChannelSnapshot.from_api(item) for item in items}
        window = ObservationWindow.ending_at(reference_date, self._policy.window_days)
        records: list[EligibilityRecord] = []
        for candidate in batch:
            snapshot = snapshots.get(candidate.channel_id)
            record = self._evaluate_one(candidate, snapshot, window, reference_date)
            self._repository.save_eligibility(record)
            records.append(record)
        return records

    def _evaluate_one(self, candidate: CandidateRecord, snapshot: ChannelSnapshot | None, window: ObservationWindow, reference_date: date) -> EligibilityRecord:
        """Screens and, if needed, measures one candidate."""
        if snapshot is None:
            return self._build_record(candidate.channel_id, reference_date, EvaluationStage.NOT_FOUND, EligibilityStatus.FAILED, ["NOT_FOUND"], [], [], None, {})
        metrics = ChannelMetrics(snapshot.subscriber_count, snapshot.is_subscriber_count_hidden, snapshot.is_made_for_kids)
        type_result = self._screener.check(snapshot)
        screening_failures = self._screen(candidate, snapshot, type_result)
        if screening_failures:
            return self._build_record(snapshot.channel_id, reference_date, EvaluationStage.SCREENED, EligibilityStatus.FAILED, screening_failures, [], [type_result], metrics, asdict(snapshot))

        metrics = self._measure(snapshot, window)
        results = [c.check(metrics, self._policy) for c in self._criteria] + [type_result]
        status, failed, pending = summarize_outcomes(results)
        return self._build_record(snapshot.channel_id, reference_date, EvaluationStage.MEASURED, status, failed, pending, results, metrics, asdict(snapshot))

    def _screen(self, candidate: CandidateRecord, snapshot: ChannelSnapshot, type_result: CriterionResult) -> list[str]:
        """Returns the criteria that already fail without measuring uploads (empty means: measure)."""
        failures: list[str] = []
        screening = self._policy.screening
        if type_result.outcome is CriterionOutcome.FAIL:
            failures.append("C6")
        texts = [snapshot.title, snapshot.description, *candidate.evidence_titles]
        if screening.require_any_kana and not any(contain_kana(t) for t in texts):
            failures.append("C1")
        if snapshot.subscriber_count is None or snapshot.subscriber_count < screening.measurement_floor_subscribers:
            failures.append("C4")
        return failures

    def _measure(self, snapshot: ChannelSnapshot, window: ObservationWindow) -> ChannelMetrics:
        """Reads the uploads playlist back to the window start (plus buffer) and measures the videos."""
        screening = self._policy.screening
        since = window.start - timedelta(days=screening.playlist_buffer_days)
        playlist = self._client.read_playlist_since(snapshot.uploads_playlist_id, since, screening.max_playlist_pages, Lane.L3_ELIGIBILITY)
        video_ids = []
        for item in playlist.items:
            details = item.get("contentDetails", {})
            published = parse_api_datetime(details.get("videoPublishedAt"))
            if published is not None and published >= since:
                video_ids.append(details["videoId"])
        videos = [VideoSnapshot.from_api(v) for v in self._client.list_videos(video_ids, Lane.L3_ELIGIBILITY)]
        return self._calculator.calculate(snapshot, videos, window, len(playlist.items), playlist.is_truncated)

    def _build_record(
        self,
        channel_id: str,
        reference_date: date,
        stage: str,
        status: str,
        failed: list[str],
        pending: list[str],
        results: list[CriterionResult],
        metrics: ChannelMetrics | None,
        channel: dict[str, object],
    ) -> EligibilityRecord:
        """Assembles a catalog record."""
        return EligibilityRecord(
            channel_id=channel_id,
            policy_version=self._policy.policy_version,
            reference_date=reference_date.isoformat(),
            evaluated_at=self._clock().isoformat(),
            stage=stage,
            status=status,
            failed_criteria=failed,
            pending_criteria=pending,
            criteria={r.criterion_id: {"outcome": r.outcome.value, "value": r.value} for r in results},
            metrics=metrics.to_json_dict() if metrics else {},
            channel=channel,
        )
