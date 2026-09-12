from __future__ import annotations
from pathlib import Path
import yaml
from pydantic import BaseModel


class StageFlags(BaseModel):
    forensics: bool = True
    blind_base_rate: bool = True
    evidence_table: bool = True
    ach_forecast: bool = True
    devils_advocate: bool = True


class Member(BaseModel):
    name: str
    model: str
    temperature: float = 0.5


class Models(BaseModel):
    forecast_tier: str
    cheap_tier: str
    web_search: str
    anthropic_fallback: str
    members: list[Member]


class Limits(BaseModel):
    per_call_usd: float = 0.40
    per_question_usd: float = 1.0
    season_usd: float = 500.0
    question_wall_clock_s: int = 600
    da_skip_at_budget_fraction: float = 0.7
    min_members: int = 2
    max_questions_per_run: int = 15
    max_concurrent_questions: int = 3


class ForecastCfg(BaseModel):
    p_min: float = 0.01
    p_max: float = 0.99
    mc_floor: float = 0.01
    da_max_logit_shift: float = 0.5
    numeric_percentiles: list[int] = [5, 10, 20, 40, 60, 80, 90, 95]


class ResearchCfg(BaseModel):
    asknews_enabled: bool = True
    web_search_enabled: bool = True
    resolution_fetch_enabled: bool = True
    max_queries: int = 5
    provider_timeout_s: int = 90
    source_text_max_chars: int = 6000


class Tournaments(BaseModel):
    fall: int | str
    minibench: int | str
    cup: int | str
    test: int | str


class CommentCfg(BaseModel):
    max_chars: int = 3000


class Settings(BaseModel):
    stages: StageFlags
    models: Models
    limits: Limits
    forecast: ForecastCfg
    research: ResearchCfg
    tournaments: Tournaments
    comment: CommentCfg


def load_settings(path: str = "config.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return Settings.model_validate(data)
