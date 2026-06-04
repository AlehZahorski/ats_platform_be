from __future__ import annotations

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


class OverviewReport(BaseModel):
    """Top-level KPIs for the selected window."""
    total_applications: int
    total_hired: int
    hire_rate: float  # % of applications that reached "hired"
    avg_time_to_hire_days: float
    active_jobs: int


class TimeSeriesPoint(BaseModel):
    date: str  # ISO date (YYYY-MM-DD)
    count: int


class ApplicationsOverTimeReport(BaseModel):
    points: list[TimeSeriesPoint]
    total: int


class JobApplicationsRow(BaseModel):
    job_id: str
    job_title: str
    count: int
    percentage: float


class JobApplicationsReport(BaseModel):
    jobs: list[JobApplicationsRow]
    total: int
