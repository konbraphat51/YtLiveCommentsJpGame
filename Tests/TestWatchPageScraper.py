"""Tests of the watch-page parser on synthetic ytInitialData shapes."""

from __future__ import annotations

from GameChatCollector.Sources.WatchPageScraper import parse_watch_facts


def test_replay_and_game_card_are_detected() -> None:
    card = {"richMetadataRenderer": {"style": "RICH_METADATA_RENDERER_STYLE_BOX_ART", "title": {"simpleText": "Minecraft"}, "endpoint": {"browseEndpoint": {"browseId": "UCQvWX73GQygcwXOTSf_VDVg"}}}}
    data = {"contents": {"twoColumnWatchNextResults": {"conversationBar": {"liveChatRenderer": {"isReplay": True}}, "results": {"results": {"contents": [{"x": [card]}]}}}}}
    facts = parse_watch_facts("v", data)
    assert facts.is_chat_replay_available
    assert facts.game_card_title == "Minecraft"
    assert facts.game_card_browse_id == "UCQvWX73GQygcwXOTSf_VDVg"


def test_disabled_replay_has_no_live_chat_renderer() -> None:
    data = {"contents": {"twoColumnWatchNextResults": {"conversationBar": {"conversationBarRenderer": {"availabilityMessage": {}}}}}}
    facts = parse_watch_facts("v", data)
    assert not facts.is_chat_replay_available
    assert facts.game_card_title is None
