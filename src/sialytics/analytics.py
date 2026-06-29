"""Métricas académicas para las vistas orientadas al estudiante."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from .models import CourseAttempt

PASSING_GRADE = 3.0


@dataclass(frozen=True, slots=True)
class SemesterMetrics:
    semester: str
    courses: tuple[CourseAttempt, ...]
    course_count: int
    credits: float
    pappi: float | None
    cumulative_papa: float | None
    passed: int
    failed: int
    highest_grade: float | None
    lowest_grade: float | None
    median_grade: float | None
    credits_by_type: tuple[tuple[str, float], ...]


def semester_key(period: str) -> str:
    match = re.match(r"^(\d{4}-[12]S)\b", period, flags=re.IGNORECASE)
    return match.group(1) if match is not None else period


def _numeric_attempts(courses: tuple[CourseAttempt, ...]) -> list[tuple[float, float]]:
    return [
        (course.grade.value, course.credits.value)
        for course in courses
        if isinstance(course.grade.value, float)
        and isinstance(course.credits.value, float)
        and course.credits.value > 0
    ]


def _cancelled_with_credit_loss(course: CourseAttempt) -> bool:
    values = [course.grade, *course.extra_fields.values()]
    return any(
        isinstance(value.value, str) and "CANCELADA CON PÉRDIDA DE CRÉDITOS" in value.value.upper()
        for value in values
    )


def _course_result(course: CourseAttempt) -> str | None:
    result = course.extra_fields.get("Resultado")
    if result is not None and isinstance(result.value, str):
        return result.value.upper()
    if isinstance(course.grade.value, str):
        return course.grade.value.upper()
    return None


def weighted_average(courses: tuple[CourseAttempt, ...]) -> float | None:
    attempts = _numeric_attempts(courses)
    cancelled_credits = sum(
        course.credits.value
        for course in courses
        if _cancelled_with_credit_loss(course) and isinstance(course.credits.value, float)
    )
    credits = sum(item[1] for item in attempts) + cancelled_credits
    if credits == 0:
        return None
    return round(sum(grade * weight for grade, weight in attempts) / credits, 3)


def calculate_semester_metrics(courses: list[CourseAttempt]) -> list[SemesterMetrics]:
    grouped: dict[str, list[CourseAttempt]] = {}
    for course in courses:
        if isinstance(course.period.value, str):
            grouped.setdefault(semester_key(course.period.value), []).append(course)

    cumulative: list[CourseAttempt] = []
    metrics: list[SemesterMetrics] = []
    for semester, semester_courses_list in sorted(grouped.items()):
        semester_courses = tuple(semester_courses_list)
        cumulative.extend(semester_courses)
        numeric_grades = [
            course.grade.value
            for course in semester_courses
            if isinstance(course.grade.value, float)
        ]
        passed = sum(
            _course_result(course) == "APROBADA"
            or (
                _course_result(course) is None
                and isinstance(course.grade.value, float)
                and course.grade.value >= PASSING_GRADE
            )
            for course in semester_courses
        )
        failed = sum(
            _course_result(course) in {"NO APROBADA", "REPROBADA"}
            or (
                _course_result(course) is None
                and isinstance(course.grade.value, float)
                and course.grade.value < PASSING_GRADE
            )
            for course in semester_courses
        )
        credits_by_type: dict[str, float] = {}
        for course in semester_courses:
            if isinstance(course.course_type.value, str) and isinstance(
                course.credits.value, float
            ):
                credits_by_type[course.course_type.value] = (
                    credits_by_type.get(course.course_type.value, 0.0) + course.credits.value
                )
        metrics.append(
            SemesterMetrics(
                semester=semester,
                courses=semester_courses,
                course_count=len(semester_courses),
                credits=sum(
                    course.credits.value
                    for course in semester_courses
                    if isinstance(course.credits.value, float)
                ),
                pappi=weighted_average(semester_courses),
                cumulative_papa=weighted_average(tuple(cumulative)),
                passed=passed,
                failed=failed,
                highest_grade=max(numeric_grades, default=None),
                lowest_grade=min(numeric_grades, default=None),
                median_grade=round(median(numeric_grades), 3) if numeric_grades else None,
                credits_by_type=tuple(sorted(credits_by_type.items())),
            )
        )
    return metrics


def calculate_papa(courses: list[CourseAttempt]) -> float | None:
    return weighted_average(tuple(courses))


def calculate_pappi(courses: list[CourseAttempt]) -> float | None:
    metrics = calculate_semester_metrics(courses)
    return metrics[-1].pappi if metrics else None
