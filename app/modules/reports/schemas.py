from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TimeToHireReport(BaseModel):
    avg_days: float
    min_days: float
    max_days: float
    total_hired: int


class PipelineStageReport(BaseModel):
    stage_name: str
    count: int
    percentage: float


class PipelineReport(BaseModel):
    stages: list[PipelineStageReport]
    total: int


class SourceReport(BaseModel):
    source: str
    count: int
    percentage: float


class SourcesReport(BaseModel):
    sources: list[SourceReport]
    total: int