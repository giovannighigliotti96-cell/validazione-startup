"""Pydantic models: API payloads + the internal RawSignal shape shared by all scrapers."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Source = Literal["reddit", "hackernews", "indiehackers", "trustpilot", "playstore", "appstore", "youtube", "forum"]
SignalType = Literal["post", "comment", "review", "story"]


class RawSignal(BaseModel):
    """What every scraper returns. Persisted 1:1 into raw_signals (+ heuristic flags)."""
    source: Source
    signal_type: SignalType
    external_id: str
    parent_external_id: str | None = None
    url: str | None = None
    title: str | None = None
    text: str
    lang: str | None = None
    author_hash: str | None = None
    published_at: datetime | None = None
    score: int | None = None
    num_comments: int | None = None
    rating: float | None = None
    engagement: dict[str, Any] = Field(default_factory=dict)
    keyword: str | None = None
    channel: str | None = None
    raw: dict[str, Any] | None = None


# --------------------------- keyword sets ---------------------------------
class KeywordSetIn(BaseModel):
    name: str
    description: str | None = None
    vertical: str | None = None
    is_active: bool = True
    keywords: list[str] = Field(default_factory=list)
    sources: dict[str, Any] = Field(default_factory=dict)


class KeywordSetPatch(BaseModel):
    description: str | None = None
    vertical: str | None = None
    is_active: bool | None = None
    keywords: list[str] | None = None
    sources: dict[str, Any] | None = None


# --------------------------- runs -----------------------------------------
class RunRequest(BaseModel):
    keyword_set_ids: list[str] | None = None   # None = all active
    sources: list[str] | None = None           # None = all configured in the keyword set
    trigger: Literal["manual", "cron", "github_actions"] = "manual"


# --------------------------- clusters / opportunities ---------------------
class ClusterIn(BaseModel):
    name: str
    keyword_set_id: str | None = None
    problem_statement: str | None = None
    vertical: str | None = None
    persona: str | None = None
    signal_ids: list[str] = Field(default_factory=list)


class MarketComponentIn(BaseModel):
    component: Literal["n_entities", "annual_spend", "geo_share", "segment_share", "capture_share"]
    value: float
    unit: str | None = None
    source_url: str | None = None
    method: str | None = None
    confidence: Literal["low", "medium", "high"] = "low"
    notes: str | None = None


class OpportunityPatch(BaseModel):
    competitor_count: int | None = None
    leader_reviews: int | None = None
    saturation: Literal["blue", "purple", "red"] | None = None
    saturation_notes: str | None = None
    founder_fit: int | None = Field(default=None, ge=1, le=5)
    acquisition_channel: str | None = None
    acquisition_channel_reachable: bool | None = None
    barriers: dict[str, bool] | None = None
    why_now: str | None = None
    prior_failed_attempts: str | None = None
    notes: str | None = None
    is_archived: bool | None = None
    archive_reason: str | None = None


class CompetitorIn(BaseModel):
    cluster_id: str | None = None
    keyword_set_id: str | None = None
    source: str = "manual"
    external_id: str | None = None
    name: str
    url: str | None = None
    tagline: str | None = None
    launched_at: str | None = None
    founded_year: int | None = None
    reviews_count: int | None = None
    rating: float | None = None
    pricing_monthly_usd: float | None = None
    funding_usd: float | None = None
    is_dead: bool | None = None
    search_volume: int | None = None
    cpc_usd: float | None = None
    competition: str | None = None
    notes: str | None = None


class ExperimentIn(BaseModel):
    cluster_id: str
    type: Literal["interview", "landing_page", "ads_smoke", "presale", "concierge", "other"]
    status: Literal["planned", "running", "done", "cancelled"] = "planned"
    platform: str | None = None
    cost_eur: float = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    outcome: Literal["positive", "negative", "inconclusive"] | None = None
    notes: str | None = None
    source_signal_ids: list[str] = Field(default_factory=list)


class FunnelStagePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    criteria: dict[str, Any] | None = None
    notify: bool | None = None
