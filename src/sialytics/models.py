"""Contratos de datos independientes de Playwright y Excel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Availability(StrEnum):
    AVAILABLE = "Disponible"
    NOT_AVAILABLE = "No disponible"
    NO_RECORDED_INFORMATION = "Sin información registrada"


@dataclass(frozen=True, slots=True)
class Provenance:
    source_url: str
    section: str
    official_label: str
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OfficialValue:
    status: Availability
    provenance: Provenance
    value: str | float | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.status is Availability.AVAILABLE and self.value is None:
            raise ValueError("Un valor disponible no puede ser nulo")
        if self.status is not Availability.AVAILABLE and self.value is not None:
            raise ValueError("Una ausencia oficial no puede contener un valor")

    @property
    def display_value(self) -> str | float:
        if self.status is Availability.AVAILABLE:
            if self.value is None:
                raise RuntimeError("OfficialValue incumplió su invariante")
            return self.value
        return self.status.value


@dataclass(frozen=True, slots=True)
class Program:
    program_id: str
    name: str
    study_plan: str | None = None


@dataclass(frozen=True, slots=True)
class Student:
    program: Program
    fields: dict[str, OfficialValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CourseAttempt:
    period: OfficialValue
    code: OfficialValue
    name: OfficialValue
    credits: OfficialValue
    grade: OfficialValue
    course_type: OfficialValue
    extra_fields: dict[str, OfficialValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AcademicPeriod:
    name: str
    fields: dict[str, OfficialValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CreditSummary:
    typology: OfficialValue
    required: OfficialValue
    passed: OfficialValue
    pending: OfficialValue
    enrolled: OfficialValue
    taken: OfficialValue


@dataclass(frozen=True, slots=True)
class Indicator:
    canonical_name: str
    acronym: str | None
    official_value: OfficialValue
    period: str | None = None


@dataclass(frozen=True, slots=True)
class SectionEvidence:
    section: str
    structure_id: str
    source_url: str
    recognized: bool
    headers: tuple[str, ...]
    pages_visited: int
    pagination_complete: bool
    record_count: int
    explicit_empty_status: Availability | None = None


@dataclass(slots=True)
class AcademicRecord:
    student: Student
    courses: list[CourseAttempt]
    periods: list[AcademicPeriod]
    indicators: list[Indicator]
    evidence: dict[str, SectionEvidence]
    extracted_at: datetime
    credit_summaries: list[CreditSummary] = field(default_factory=list)
    source_version: str = "sia-adf-v1"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    section: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    valid: bool
    issues: tuple[ValidationIssue, ...]
