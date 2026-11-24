"""Typed model of Config/ChannelPolicy.yaml, the versioned channel inclusion policy."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ClassificationSettings(BaseModel):
    """Rules that classify a video as a live stream and as a game stream."""

    model_config = ConfigDict(frozen=True)

    min_live_duration_minutes: int = Field(ge=0)
    game_category_ids: tuple[int, ...]


class CriteriaThresholds(BaseModel):
    """Thresholds of criteria C1-C5."""

    model_config = ConfigDict(frozen=True)

    c1_min_kana_title_share: float = Field(ge=0, le=1)
    c2_min_game_streams: int = Field(ge=0)
    c3_min_game_share: float = Field(ge=0, le=1)
    c4_min_subscribers: int = Field(ge=0)
    c5_min_chat_replay_share: float = Field(ge=0, le=1)
    c5_sample_size: int = Field(ge=1)


class ScreeningSettings(BaseModel):
    """Cheap pre-checks that skip the full measurement for hopeless candidates."""

    model_config = ConfigDict(frozen=True)

    measurement_floor_subscribers: int = Field(ge=0)
    require_any_kana: bool
    max_playlist_pages: int = Field(ge=1)
    playlist_buffer_days: int = Field(ge=0)


class ChannelTypeSettings(BaseModel):
    """Keyword lists that raise C6 flags for human review."""

    model_config = ConfigDict(frozen=True)

    clip_keywords: tuple[str, ...]
    official_keywords: tuple[str, ...]


class SearchFrameSettings(BaseModel):
    """Parameters of the search.list sampling frame."""

    model_config = ConfigDict(frozen=True)

    lookback_hours: int = Field(ge=1)
    hour_step: int = Field(ge=1)
    max_results: int = Field(ge=1, le=50)
    region_code: str
    relevance_language: str
    video_category_id: str


class ChannelPolicy(BaseModel):
    """The complete, versioned channel inclusion policy."""

    model_config = ConfigDict(frozen=True)

    policy_version: str
    hash_salt: str
    window_days: int = Field(ge=1)
    classification: ClassificationSettings
    criteria: CriteriaThresholds
    screening: ScreeningSettings
    channel_type: ChannelTypeSettings
    search_frame: SearchFrameSettings

    @classmethod
    def load(cls, path: Path) -> ChannelPolicy:
        """Loads and validates a policy YAML file.

        Args:
            path: Path to the YAML file.
        """
        with path.open(encoding="utf-8") as file:
            return cls.model_validate(yaml.safe_load(file))
