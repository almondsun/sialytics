from pathlib import Path

import pytest

from sialytics.models import Availability
from sialytics.parsing import (
    COURSES_SPEC,
    UnknownStructureError,
    detect_explicit_empty,
    find_recognized_table,
    official_value,
    parse_adf_partial_response,
    parse_course_grade,
    recognized_indicator,
    split_assignment,
)

FIXTURES = Path(__file__).parent / "fixtures"
SOURCE = "https://sia.unal.edu.co/ServiciosApp/faces/historia"


def test_parse_recognized_courses_table() -> None:
    headers, rows = find_recognized_table((FIXTURES / "courses.html").read_text(), COURSES_SPEC)
    assert headers[0] == "Asignaturas"
    assert rows[0]["grade"] == "4,5"
    assert rows[1]["assignment"] == "=RIESGO (100002)"
    assert split_assignment(rows[0]["assignment"]) == ("Introducción", "100001")
    assert split_assignment("Física (1000017-Z)") == ("Física", "1000017-Z")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.8\nAPROBADA", (4.8, "APROBADA")),
        ("2,7 NO APROBADA", (2.7, "NO APROBADA")),
        ("APROBADA", (None, "APROBADA")),
        (
            "CANCELADA CON PÉRDIDA DE CRÉDITOS",
            (None, "CANCELADA CON PÉRDIDA DE CRÉDITOS"),
        ),
    ],
)
def test_course_grade_separates_numeric_value_and_result(
    raw: str, expected: tuple[float | None, str | None]
) -> None:
    assert parse_course_grade(raw) == expected


def test_empty_cell_is_not_an_official_absence() -> None:
    with pytest.raises(UnknownStructureError):
        official_value("", source_url=SOURCE, section="Indicadores", label="PAPA")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("No disponible", Availability.NOT_AVAILABLE),
        ("Sin información registrada", Availability.NO_RECORDED_INFORMATION),
    ],
)
def test_official_absence_is_preserved(text: str, expected: Availability) -> None:
    value = official_value(text, source_url=SOURCE, section="Indicadores", label="PAPA")
    assert value.status is expected
    assert value.display_value == expected.value


def test_explicit_empty_detection_does_not_accept_blank_html() -> None:
    assert detect_explicit_empty("<div></div>") is None
    assert (
        detect_explicit_empty("<p>Sin información registrada</p>")
        is Availability.NO_RECORDED_INFORMATION
    )
    assert detect_explicit_empty("<p>Estado: No disponible temporalmente</p>") is None


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_are_rejected(text: str) -> None:
    with pytest.raises(UnknownStructureError):
        official_value(
            text,
            source_url=SOURCE,
            section="Indicadores",
            label="PAPA",
            numeric=True,
        )


def test_only_known_indicators_are_accepted() -> None:
    assert recognized_indicator("PAPA") == ("Promedio Aritmético Ponderado Acumulado", "PAPA")
    with pytest.raises(UnknownStructureError, match="no reconocido"):
        recognized_indicator("GPA")


def test_adf_partial_response_requires_unique_updates() -> None:
    updates = parse_adf_partial_response(
        "<partial-response><changes><update id='panel'><![CDATA[<p>ok</p>]]>"
        "</update><update id='javax.faces.ViewState'>state</update></changes></partial-response>"
    )
    assert updates["panel"] == "<p>ok</p>"
    with pytest.raises(UnknownStructureError):
        parse_adf_partial_response("<html />")
