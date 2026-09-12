from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Kind = Literal["binary", "multiple_choice", "numeric", "date", "discrete"]


class ForecastValue(BaseModel):
    kind: Kind
    probability: float | None = None                 # binary
    options: dict[str, float] | None = None          # multiple_choice
    percentiles: dict[int, float] | None = None      # numeric/discrete/date: percentile -> value


class QuestionSummary(BaseModel):
    post_id: int
    question_id: int
    url: str
    title: str
    kind: Kind
    close_time: str | None
    options: list[str] | None
    lower_bound: float | None
    upper_bound: float | None
    open_lower: bool | None
    open_upper: bool | None
    cdf_size: int | None
    zero_point: float | None
    unit: str | None


class Forensics(BaseModel):
    resolution_statement: str
    status_quo_outcome: str
    key_dates: list[str] = []
    traps: list[str] = []
    possibly_already_resolved: bool = False
    already_resolved_reason: str = ""
    search_queries: list[str] = []
    things_that_do_not_count: list[str] = []


class BlindEstimate(BaseModel):
    reference_class: str
    base_rate_reasoning: str
    forecast: ForecastValue


class RawSource(BaseModel):
    provider: str
    url: str | None = None
    title: str | None = None
    published: str | None = None
    text: str


class ResearchBundle(BaseModel):
    sources: list[RawSource] = []
    diagnostics: dict[str, str] = {}


class Evidence(BaseModel):
    claim: str
    source: str
    date: str | None = None
    reliability: Literal["A", "B", "C", "D", "E", "F"]
    credibility: int = Field(ge=1, le=6)
    supports: str            # outcome label, or "context"
    note: str = ""


class EvidenceTable(BaseModel):
    items: list[Evidence] = []
    already_resolved_signal: str = ""


class MemberForecast(BaseModel):
    name: str
    model: str
    forecast: ForecastValue
    reasoning: str
    stated_number: float | None = None
    cost_usd: float = 0.0
    dropped_reason: str | None = None


class Aggregate(BaseModel):
    pre_da: ForecastValue
    post_da: ForecastValue | None = None
    method: str
    da_critique: str | None = None


class StageCost(BaseModel):
    stage: str
    model: str
    cost_usd: float
    seconds: float


class ForecastRecord(BaseModel):
    question: QuestionSummary
    run_ts: str
    flags: dict[str, bool]
    forensics: Forensics | None = None
    blind: BlindEstimate | None = None
    research: ResearchBundle | None = None
    evidence: EvidenceTable | None = None
    members: list[MemberForecast] = []
    aggregate: Aggregate | None = None
    final: ForecastValue | None = None
    comment: str | None = None
    stage_costs: list[StageCost] = []
    cost_usd: float = 0.0
    guards_fired: list[str] = []
    published: bool = False
    error: str | None = None
