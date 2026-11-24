"""Command-line entry point (`collector`)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from GameChatCollector.Operations.PriorityRules import DiscoveryPriorityRule, EligibilityPriorityRule
from GameChatCollector.Operations.QuotaBudget import QuotaBudget, to_quota_day
from GameChatCollector.Operations.QuotaSettings import Lane, QuotaSettings
from GameChatCollector.Selection.ApiSearchCandidateSource import ApiSearchCandidateSource
from GameChatCollector.Selection.CandidateSources import CsvCandidateSource
from GameChatCollector.Selection.ChannelEligibilityEvaluator import ChannelEligibilityEvaluator
from GameChatCollector.Selection.ChannelPolicy import ChannelPolicy
from GameChatCollector.Selection.ChannelTypeScreener import ChannelTypeReviewBook, ChannelTypeScreener
from GameChatCollector.Selection.CohortReporter import CohortReporter
from GameChatCollector.Selection.EligibilityCriteria import build_default_criteria
from GameChatCollector.Settings import Settings
from GameChatCollector.Sources.YouTubeApiClient import YouTubeApiClient
from GameChatCollector.Storage.CatalogRepository import CatalogRepository
from GameChatCollector.Storage.RawStore import RawStore

app = typer.Typer(help="GameChatCollector command-line interface.", no_args_is_help=True)
channels_app = typer.Typer(help="Channel selection (Docs/ChannelPolicy.md).", no_args_is_help=True)
app.add_typer(channels_app, name="channels")

ReferenceOption = Annotated[str, typer.Option(help="Reference date YYYY-MM-DD (end of the observation window).")]
ProfileOption = Annotated[str | None, typer.Option(help="Quota lane profile in Config/ApiQuota.yaml (default: active_profile).")]


class Context:
    """Wires settings, configuration and services for one command."""

    def __init__(self, profile: str | None = None) -> None:
        """Loads settings and configuration files."""
        self.settings = Settings()
        config = self.settings.config_dir
        self.policy = ChannelPolicy.load(config / "ChannelPolicy.yaml")
        self.quota = QuotaSettings.load(config / "ApiQuota.yaml")
        self.repository = CatalogRepository(self.settings.catalog_path)
        self.budget = QuotaBudget(self.quota, self.repository, profile)

    def build_client(self) -> YouTubeApiClient:
        """Creates the Data API client (requires the API key)."""
        return YouTubeApiClient(self.settings.require_api_key(), self.budget, self.quota, RawStore(self.settings.raw_dir))


@channels_app.command("discover")
def discover_channels(reference_date: ReferenceOption, points: Annotated[int, typer.Option(help="Size of the search point plan.")] = 64, max_calls: Annotated[int, typer.Option(help="Maximum search.list calls in this run.")] = 10, profile: ProfileOption = None) -> None:
    """Adds candidates from Config/ChannelCandidates.csv and from the search.list frame (lane L4)."""
    context = Context(profile)
    now = datetime.now(UTC)
    csv_new = sum(context.repository.add_discovery(c.channel_id, c.discovery_source, "csv", c.evidence_titles[0] if c.evidence_titles else "", now) for c in CsvCandidateSource(context.settings.config_dir / "ChannelCandidates.csv").discover())
    source = ApiSearchCandidateSource(context.policy, context.build_client(), context.repository, DiscoveryPriorityRule(context.quota.priority, context.policy.hash_salt))
    report = source.discover(date.fromisoformat(reference_date), points, max_calls)
    typer.echo(f"csv new={csv_new}; search points={report.points_searched} videos={report.videos_seen} new={report.new_candidates} budget_exhausted={report.is_budget_exhausted}")


@channels_app.command("evaluate")
def evaluate_channels(reference_date: ReferenceOption, max_candidates: Annotated[int, typer.Option(help="Maximum candidates to evaluate in this run.")] = 200, profile: ProfileOption = None) -> None:
    """Measures candidates not yet evaluated for this policy version and reference date (lane L3)."""
    context = Context(profile)
    screener = ChannelTypeScreener(context.policy, ChannelTypeReviewBook.load(context.settings.config_dir / "ChannelTypeReviews.csv"))
    evaluator = ChannelEligibilityEvaluator(context.policy, context.build_client(), context.repository, build_default_criteria(), screener, EligibilityPriorityRule(context.quota.priority, context.policy.hash_salt))
    report = evaluator.evaluate_pending_candidates(date.fromisoformat(reference_date), max_candidates)
    typer.echo(f"evaluated={report.evaluated} by_status={report.counts_by_status} budget_exhausted={report.is_budget_exhausted}")


@channels_app.command("report")
def report_channels(reference_date: ReferenceOption, out: Annotated[Path, typer.Option(help="Output directory.")] = Path("Cohorts")) -> None:
    """Writes ChannelEligibility.csv, Cohort.csv and Summary.md for the policy version and reference date."""
    context = Context()
    records = list(context.repository.iterate_eligibility(context.policy.policy_version, reference_date))
    directory = out / f"Policy{context.policy.policy_version}_{reference_date.replace('-', '')}"
    files = CohortReporter(context.policy).write(records, context.repository.list_candidates(), directory)
    typer.echo(f"wrote {files.eligibility_csv}, {files.cohort_csv}, {files.summary_md}")


@app.command("status")
def show_status(profile: ProfileOption = None) -> None:
    """Prints Data API units spent and remaining per lane on the current Pacific-time quota day."""
    context = Context(profile)
    now = datetime.now(UTC)
    usage = context.repository.load_usage(to_quota_day(now))
    for lane in Lane:
        typer.echo(f"{lane.value}: spent={usage.get(lane, 0)} remaining={context.budget.remaining(lane, now)}")


if __name__ == "__main__":
    app()
