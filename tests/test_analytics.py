from datetime import UTC, datetime

from sialytics.analytics import calculate_papa, calculate_pappi, calculate_semester_metrics
from sialytics.models import Availability, CourseAttempt, OfficialValue, Provenance

SOURCE = "https://sia.unal.edu.co/ServiciosApp/faces/historia"
NOW = datetime(2026, 1, 2, tzinfo=UTC)


def value(label: str, raw: str | float) -> OfficialValue:
    return OfficialValue(
        Availability.AVAILABLE,
        Provenance(SOURCE, "Prueba", label, NOW),
        raw,
    )


def course(
    period: str,
    code: str,
    credits: float,
    grade: str | float,
    result: str | None = None,
) -> CourseAttempt:
    return CourseAttempt(
        period=value("Periodo", period),
        code=value("Código", code),
        name=value("Asignatura", f"Asignatura {code}"),
        credits=value("Créditos", credits),
        grade=value("Calificación", grade),
        course_type=value("Tipo", "Disciplinar"),
        extra_fields={"Resultado": value("Resultado", result)} if result else {},
    )


def test_semester_statistics_and_cumulative_papa() -> None:
    courses = [
        course("2025-1S Ordinaria", "1", 3.0, 4.0),
        course("2025-1S Validación por suficiencia", "2", 1.0, 2.0),
        course("2025-2S Ordinaria", "3", 2.0, 5.0),
    ]

    metrics = calculate_semester_metrics(courses)

    assert [item.semester for item in metrics] == ["2025-1S", "2025-2S"]
    assert metrics[0].pappi == 3.5
    assert metrics[0].cumulative_papa == 3.5
    assert metrics[0].passed == 1
    assert metrics[0].failed == 1
    assert metrics[1].cumulative_papa == 4.0
    assert calculate_papa(courses) == 4.0
    assert calculate_pappi(courses) == 5.0


def test_non_numeric_grades_do_not_distort_average() -> None:
    courses = [
        course("2025-1S", "1", 3.0, 4.0),
        course("2025-1S", "2", 4.0, "AP"),
    ]

    metrics = calculate_semester_metrics(courses)

    assert metrics[0].pappi == 4.0
    assert metrics[0].credits == 7.0
    assert metrics[0].passed == 1
    assert metrics[0].failed == 0


def test_academic_results_are_counted_and_credit_loss_affects_weighting() -> None:
    courses = [
        course("2025-1S", "1", 3.0, 4.0, "APROBADA"),
        course("2025-1S", "2", 2.0, "APROBADA", "APROBADA"),
        course(
            "2025-1S",
            "3",
            1.0,
            "CANCELADA CON PÉRDIDA DE CRÉDITOS",
            "CANCELADA CON PÉRDIDA DE CRÉDITOS",
        ),
    ]

    metrics = calculate_semester_metrics(courses)

    assert metrics[0].pappi == 3.0
    assert metrics[0].cumulative_papa == 3.0
    assert metrics[0].passed == 2
    assert metrics[0].failed == 0
