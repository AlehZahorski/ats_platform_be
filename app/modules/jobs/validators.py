"""Job validators — publish readiness and status transitions.

Both validators are stateless. They accept either an ORM `Job` instance or a
plain dict (e.g. merged update state), thanks to the `_attr` helper.
"""
from __future__ import annotations

import re
from typing import Any

from app.core.enums.jobs import JobStatus
from app.core.exceptions import UnprocessableError
from app.core.i18n import t


def _attr(state: Any, key: str) -> Any:
    """Read attribute from dict or object uniformly."""
    if isinstance(state, dict):
        return state.get(key)
    return getattr(state, key, None)


def _has_text(value: Any) -> bool:
    return bool(value and str(value).strip())


def _html_has_content(value: Any) -> bool:
    if not value:
        return False
    text = re.sub(r"<[^>]+>", "", str(value)).strip()
    return bool(text)


def _publish_requirements() -> dict[str, str]:
    return {
        "role_summary":      t("jobs.publish.role_summary_required"),
        "role_purpose":      t("jobs.publish.role_purpose_required"),
        "responsibilities":  t("jobs.publish.responsibilities_required"),
        "must_haves":        t("jobs.publish.must_haves_required"),
        "nice_to_haves":     t("jobs.publish.nice_to_haves_required"),
        "tech_stack":        t("jobs.publish.tech_stack_required"),
        "seniority":         t("jobs.publish.seniority_required"),
        "team_context":      t("jobs.publish.team_context_required"),
        "benefits":          t("jobs.publish.benefits_required"),
        "salary":            t("jobs.publish.salary_required"),
        "work_mode":         t("jobs.publish.work_mode_required"),
        "contract_type":     t("jobs.publish.contract_type_required"),
        "location_clarity":  t("jobs.publish.location_clarity_required"),
        "value_proposition": t("jobs.publish.value_proposition_required"),
        "hiring_process":    t("jobs.publish.hiring_process_required"),
    }


# ───────────────────────────────────────────────────────────────────────────
# Publish validator — checks if a job is ready to go from draft → open
# ───────────────────────────────────────────────────────────────────────────

class PublishValidator:
    """Validates that a job offer meets all requirements for publication.

    Each rule lives in its own private method for clarity. `validate()`
    aggregates them and returns a list of localized issue messages (empty
    list = ready to publish).
    """

    @classmethod
    def validate(cls, job_state: Any) -> list[str]:
        reqs = _publish_requirements()
        return [
            *cls._check_role(job_state, reqs),
            *cls._check_responsibilities(job_state, reqs),
            *cls._check_requirements_extras(job_state, reqs),
            *cls._check_seniority_and_team(job_state, reqs),
            *cls._check_salary(job_state, reqs),
            *cls._check_work_conditions(job_state, reqs),
            *cls._check_value(job_state, reqs),
        ]

    @staticmethod
    def _check_requirements_extras(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _html_has_content(_attr(state, "nice_to_haves")):
            issues.append(reqs["nice_to_haves"])
        if not _html_has_content(_attr(state, "tech_stack")):
            issues.append(reqs["tech_stack"])
        return issues

    @staticmethod
    def _check_seniority_and_team(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _has_text(_attr(state, "seniority")):
            issues.append(reqs["seniority"])
        if not _has_text(_attr(state, "team_context")):
            issues.append(reqs["team_context"])
        return issues

    @staticmethod
    def _check_role(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _has_text(_attr(state, "role_summary")):
            issues.append(reqs["role_summary"])
        if not _has_text(_attr(state, "role_purpose")):
            issues.append(reqs["role_purpose"])
        return issues

    @staticmethod
    def _check_responsibilities(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _html_has_content(_attr(state, "responsibilities")):
            issues.append(reqs["responsibilities"])
        if not _html_has_content(_attr(state, "must_haves")):
            issues.append(reqs["must_haves"])
        return issues

    @staticmethod
    def _check_salary(state: Any, reqs: dict[str, str]) -> list[str]:
        complete = (
            _attr(state, "salary_min") is not None
            and _attr(state, "salary_max") is not None
            and _has_text(_attr(state, "salary_currency"))
            and _has_text(_attr(state, "salary_period"))
        )
        return [] if complete else [reqs["salary"]]

    @staticmethod
    def _check_work_conditions(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _has_text(_attr(state, "work_mode")):
            issues.append(reqs["work_mode"])
        if not _has_text(_attr(state, "contract_type")):
            issues.append(reqs["contract_type"])
        has_location = _has_text(_attr(state, "location"))
        has_remote = _has_text(_attr(state, "remote_constraints"))
        if not has_location and not has_remote:
            issues.append(reqs["location_clarity"])
        return issues

    @staticmethod
    def _check_value(state: Any, reqs: dict[str, str]) -> list[str]:
        issues: list[str] = []
        if not _has_text(_attr(state, "value_proposition")):
            issues.append(reqs["value_proposition"])
        if not _html_has_content(_attr(state, "benefits")):
            issues.append(reqs["benefits"])
        if not _html_has_content(_attr(state, "hiring_process")):
            issues.append(reqs["hiring_process"])
        return issues


# ───────────────────────────────────────────────────────────────────────────
# Status transition validator — gates draft → open behind PublishValidator
# ───────────────────────────────────────────────────────────────────────────

class StatusTransitionValidator:
    """Validates that a status transition is allowed.

    Currently the only gated transition is *anything → open*, which requires
    a fully-completed offer (delegated to PublishValidator).
    """

    @classmethod
    def validate(cls, next_state: Any) -> None:
        """Raises UnprocessableError if the transition is not allowed."""
        target = _attr(next_state, "status")
        if str(target) != JobStatus.open:
            return

        issues = PublishValidator.validate(next_state)
        if issues:
            raise UnprocessableError({
                "message": t("jobs.not_ready"),
                "issues": issues,
            })
