"""End-to-end tests of discovery, evaluation and reporting against a mocked Data API."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from Factories import load_policy
from GameChatCollector.Operations.PriorityRules import DiscoveryPriorityRule, EligibilityPriorityRule
from GameChatCollector.Operations.QuotaBudget import QuotaBudget
from GameChatCollector.Operations.QuotaSettings import QuotaSettings
from GameChatCollector.Selection.ApiSearchCandidateSource import ApiSearchCandidateSource
from GameChatCollector.Selection.CandidateSources import SearchPointPlan, compute_van_der_corput
from GameChatCollector.Selection.ChannelEligibilityEvaluator import ChannelEligibilityEvaluator
from GameChatCollector.Selection.ChannelTypeScreener import ChannelTypeReviewBook, ChannelTypeScreener
from GameChatCollector.Selection.CohortReporter import CohortReporter
from GameChatCollector.Selection.EligibilityCriteria import build_default_criteria
from GameChatCollector.Sources.YouTubeApiClient import API_ROOT, YouTubeApiClient
from GameChatCollector.Storage.CatalogRepository import CatalogRepository
from GameChatCollector.Storage.RawStore import RawStore

QUOTA = QuotaSettings.load(Path(__file__).resolve().parents[1] / "Config" / "ApiQuota.yaml")
REFERENCE = date(2026, 11, 24)
NOW = datetime(2026, 11, 24, 12, tzinfo=UTC)
GOOD, SMALL, FOREIGN = "UCgood0000000000000000", "UCsmall000000000000000", "UCforeign0000000000000"


def iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_videos() -> list[dict[str, Any]]:
    videos = []
    for i in range(10):
        start = NOW - timedelta(days=3 * i + 1)
        videos.append({"id": f"g{i}", "snippet": {"channelId": GOOD, "title": f"【マイクラ】#{i}", "categoryId": "20", "publishedAt": iso(start)}, "liveStreamingDetails": {"actualStartTime": iso(start), "actualEndTime": iso(start + timedelta(hours=2))}, "statistics": {"viewCount": "1000"}})
    return videos


def handle(request: httpx.Request) -> httpx.Response:
    path, params = request.url.path.rsplit("/", 1)[-1], request.url.params
    if path == "search":
        items = [{"id": {"videoId": "s1"}, "snippet": {"channelId": GOOD, "title": "【APEX】ランク"}}, {"id": {"videoId": "s2"}, "snippet": {"channelId": SMALL, "title": "マイクラ"}}, {"id": {"videoId": "s3"}, "snippet": {"channelId": FOREIGN, "title": "Ranked grind"}}]
        return httpx.Response(200, json={"items": items})
    if path == "channels":
        stats = {GOOD: "50000", SMALL: "100", FOREIGN: "90000"}
        titles = {GOOD: "ゲーム好きの配信者", SMALL: "ちいさなch", FOREIGN: "Grinder"}
        items = [{"id": cid, "snippet": {"title": titles[cid], "description": ""}, "statistics": {"subscriberCount": stats[cid], "videoCount": "10"}, "status": {"madeForKids": False}} for cid in params["id"].split(",")]
        return httpx.Response(200, json={"items": items})
    if path == "playlistItems":
        return httpx.Response(200, json={"items": [{"contentDetails": {"videoId": v["id"], "videoPublishedAt": v["snippet"]["publishedAt"]}} for v in build_videos()]})
    if path == "videos":
        wanted = set(params["id"].split(","))
        return httpx.Response(200, json={"items": [v for v in build_videos() if v["id"] in wanted]})
    return httpx.Response(404, json={})


def test_van_der_corput_prefix_is_spread() -> None:
    assert [compute_van_der_corput(i) for i in range(1, 5)] == [0.5, 0.25, 0.75, 0.125]


def test_search_points_stay_inside_frame_and_rotate_terms() -> None:
    policy = load_policy()
    points = SearchPointPlan(policy.search_frame, REFERENCE).build_points(8)
    frame_end = datetime(2026, 11, 24, tzinfo=UTC)
    assert all(frame_end - timedelta(days=policy.search_frame.frame_days) <= p.published_before <= frame_end for p in points)
    assert [p.query_term for p in points[:4]] == list(policy.search_frame.query_terms)
    assert len({p.published_before.hour for p in points}) == 8


def test_pipeline_discovers_evaluates_and_reports(tmp_path: Path) -> None:
    policy = load_policy()
    repository = CatalogRepository(tmp_path / "Catalog.sqlite")
    budget = QuotaBudget(QUOTA, repository, profile="bootstrap")
    http = httpx.Client(base_url=API_ROOT, transport=httpx.MockTransport(handle))
    client = YouTubeApiClient("dummy", budget, QUOTA, RawStore(tmp_path / "Raw"), http=http, clock=lambda: NOW)

    report = ApiSearchCandidateSource(policy, client, repository, DiscoveryPriorityRule(QUOTA.priority, "s"), clock=lambda: NOW).discover(REFERENCE, point_count=4, max_calls=2)
    assert report.points_searched == 2 and report.new_candidates == 3

    screener = ChannelTypeScreener(policy, ChannelTypeReviewBook({}))
    evaluator = ChannelEligibilityEvaluator(policy, client, repository, build_default_criteria(), screener, EligibilityPriorityRule(QUOTA.priority, "s"), clock=lambda: NOW)
    result = evaluator.evaluate_pending_candidates(REFERENCE, max_candidates=10)
    assert result.evaluated == 3

    records = {r.channel_id: r for r in repository.iterate_eligibility(policy.policy_version, REFERENCE.isoformat())}
    assert records[GOOD].status == "PENDING" and records[GOOD].pending_criteria == ["C5"]
    assert records[SMALL].stage == "SCREENED" and records[SMALL].failed_criteria == ["C4"]
    assert records[FOREIGN].failed_criteria == ["C1"]

    files = CohortReporter(policy).write(list(records.values()), repository.list_candidates(), tmp_path / "Out")
    assert GOOD in files.cohort_csv.read_text(encoding="utf-8-sig")
    summary = files.summary_md.read_text(encoding="utf-8")
    assert "Sensitivity" in summary and "C6 review queue" in summary
    assert any((tmp_path / "Raw" / "Api").rglob("*.json.gz"))
