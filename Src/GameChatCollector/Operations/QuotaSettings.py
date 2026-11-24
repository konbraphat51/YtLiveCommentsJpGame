"""Typed model of Config/ApiQuota.yaml: lane shares, priority parameters and call costs."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Lane(StrEnum):
    """Data API budget lanes, in serving order."""

    L1_OPERATIONAL = "L1_OPERATIONAL"
    L2_BACKFILL = "L2_BACKFILL"
    L3_ELIGIBILITY = "L3_ELIGIBILITY"
    L4_DISCOVERY = "L4_DISCOVERY"


class PrioritySettings(BaseModel):
    """Parameters of the per-lane priority rules."""

    model_config = ConfigDict(frozen=True)

    imminent_minutes: int = Field(ge=0)
    grace_hours: int = Field(ge=0)
    backfill_slice_days: int = Field(ge=1)
    stable_failure_cooldown_days: int = Field(ge=0)
    variable_failure_cooldown_days: int = Field(ge=0)


class QuotaSettings(BaseModel):
    """Daily quota split into lanes."""

    model_config = ConfigDict(frozen=True)

    daily_units: int = Field(ge=1)
    reserve_share: float = Field(ge=0, le=1)
    release_hours_before_reset: int = Field(ge=0, le=24)
    active_profile: str
    profiles: dict[str, dict[Lane, float]]
    priority: PrioritySettings
    costs: dict[str, int]

    @model_validator(mode="after")
    def _validate_shares(self) -> QuotaSettings:
        """Checks that the active profile exists and that shares plus reserve do not exceed 1."""
        if self.active_profile not in self.profiles:
            raise ValueError(f"unknown profile {self.active_profile}")
        for name, shares in self.profiles.items():
            if sum(shares.values()) + self.reserve_share > 1 + 1e-9:
                raise ValueError(f"profile {name} exceeds the daily quota")
        return self

    def allotment(self, lane: Lane, profile: str | None = None) -> int:
        """Units guaranteed to a lane per day under the given (or active) profile."""
        shares = self.profiles[profile or self.active_profile]
        return int(shares.get(lane, 0.0) * self.daily_units)

    def spendable_units(self) -> int:
        """Units per day that may be spent automatically (everything except the reserve)."""
        return int((1 - self.reserve_share) * self.daily_units)

    def cost(self, method: str) -> int:
        """Units charged for one call of the method."""
        return self.costs[method]

    @classmethod
    def load(cls, path: Path) -> QuotaSettings:
        """Loads and validates a quota YAML file."""
        with path.open(encoding="utf-8") as file:
            return cls.model_validate(yaml.safe_load(file))
