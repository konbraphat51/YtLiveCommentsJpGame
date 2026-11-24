"""Re-judges stored evaluations from their saved metrics and snapshot, without any network access."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from GameChatCollector.Domain.Channel import ChannelSnapshot
from GameChatCollector.Selection.ChannelEligibilityEvaluator import EvaluationStage, summarize_outcomes
from GameChatCollector.Selection.ChannelMetrics import ChannelMetrics
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Selection.ChannelTypeScreener import ChannelTypeScreener
from GameChatCollector.Selection.EligibilityCriteria import EligibilityCriterion
from GameChatCollector.Storage.CatalogRepository import CatalogRepository, EligibilityRecord


class EligibilityRejudger:
    """Applies C1-C6 again to a measured record (for example after C5 is measured or a C6 review is logged)."""

    def __init__(self, policy: ChannelPolicy, repository: CatalogRepository, criteria: list[EligibilityCriterion], screener: ChannelTypeScreener, clock: Callable[[], datetime] | None = None) -> None:
        """Creates the rejudger."""
        self._policy = policy
        self._repository = repository
        self._criteria = criteria
        self._screener = screener
        self._clock = clock or (lambda: datetime.now(UTC))

    def rejudge(self, record: EligibilityRecord, metrics: ChannelMetrics) -> EligibilityRecord:
        """Judges the metrics of a MEASURED record, saves the updated record and returns it."""
        results = [c.check(metrics, self._policy) for c in self._criteria] + [self._screener.check(ChannelSnapshot(**record.channel))]
        status, failed, pending = summarize_outcomes(results)
        criteria = {r.criterion_id: {"outcome": r.outcome.value, "value": r.value} for r in results}
        updated = replace(record, evaluated_at=self._clock().isoformat(), status=status, failed_criteria=failed, pending_criteria=pending, criteria=criteria, metrics=metrics.to_json_dict())
        self._repository.save_eligibility(updated)
        return updated

    def rejudge_all(self, reference_date: str) -> int:
        """Re-judges every evaluation of the policy version and reference date; returns how many changed status."""
        changed = 0
        for record in list(self._repository.iterate_eligibility(self._policy.policy_version, reference_date)):
            # screened records were never measured, so only MEASURED ones can change
            if record.stage != EvaluationStage.MEASURED:
                continue
            updated = self.rejudge(record, ChannelMetrics.from_json_dict(record.metrics))
            changed += updated.status != record.status
        return changed
