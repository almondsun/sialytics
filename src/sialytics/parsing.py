"""Parseo estricto de fragmentos ADF y estructuras HTML reconocidas."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup, Tag
from defusedxml import ElementTree

from .models import Availability, OfficialValue, Provenance
from .security import NavigationPolicy


class UnknownStructureError(ValueError):
    pass


MAX_HTML_CHARACTERS = 10_000_000
MAX_ADF_CHARACTERS = 5_000_000


def _parse_html(html: str) -> BeautifulSoup:
    if len(html) > MAX_HTML_CHARACTERS:
        raise UnknownStructureError("Documento HTML excede el límite seguro")
    return BeautifulSoup(html, "lxml")


EXPLICIT_ABSENCES: dict[str, Availability] = {
    "no disponible": Availability.NOT_AVAILABLE,
    "sin informacion registrada": Availability.NO_RECORDED_INFORMATION,
    "no hay informacion registrada": Availability.NO_RECORDED_INFORMATION,
}

KNOWN_INDICATORS: dict[str, tuple[str, str | None]] = {
    "pregrado - promedio academico": ("Pregrado - Promedio académico", None),
    "promedio aritmetico ponderado acumulado": (
        "Promedio Aritmético Ponderado Acumulado",
        "PAPA",
    ),
    "papa": ("Promedio Aritmético Ponderado Acumulado", "PAPA"),
    "promedio aritmetico ponderado para inscripcion": (
        "Promedio Aritmético Ponderado para Inscripción",
        "PAPPI",
    ),
    "pappi": ("Promedio Aritmético Ponderado para Inscripción", "PAPPI"),
    "cupo de creditos": ("Cupo de créditos", None),
    "creditos aprobados": ("Créditos aprobados", None),
    "creditos pendientes": ("Créditos pendientes", None),
    "avance en el plan de estudios": ("Avance en el plan de estudios", None),
    "porcentaje de avance": ("Porcentaje de avance", None),
}


def normalize_label(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", ascii_value.strip().lower().rstrip(":"))


def parse_decimal(value: str) -> float:
    cleaned = value.strip().replace(" ", "")
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", ".")
    try:
        decimal = Decimal(cleaned)
        if not decimal.is_finite():
            raise InvalidOperation
        return float(decimal)
    except InvalidOperation as exc:
        raise UnknownStructureError(f"Valor numérico no reconocido: {value!r}") from exc


COURSE_GRADE_PATTERN = re.compile(
    r"^\s*(?:(?P<grade>\d+(?:[.,]\d+)?)\s*)?"
    r"(?P<result>APROBADA|NO APROBADA|REPROBADA|"
    r"CANCELADA CON P[EÉ]RDIDA DE CR[EÉ]DITOS)?\s*$",
    flags=re.IGNORECASE,
)


def parse_course_grade(raw: str) -> tuple[float | None, str | None]:
    """Separa la calificación numérica del resultado mostrado por SIA."""

    match = COURSE_GRADE_PATTERN.fullmatch(raw)
    if match is None or not any(match.groupdict().values()):
        raise UnknownStructureError(f"Calificación de asignatura no reconocida: {raw!r}")
    grade = match.group("grade")
    result = match.group("result")
    return (parse_decimal(grade) if grade is not None else None, result.upper() if result else None)


def official_value(
    raw: str,
    *,
    source_url: str,
    section: str,
    label: str,
    numeric: bool = False,
    unit: str | None = None,
    observed_at: datetime | None = None,
) -> OfficialValue:
    NavigationPolicy.assert_academic_source(source_url)
    provenance = Provenance(source_url, section, label, observed_at or datetime.now(UTC))
    absence = EXPLICIT_ABSENCES.get(normalize_label(raw))
    if absence is not None:
        return OfficialValue(status=absence, provenance=provenance, unit=unit)
    stripped = raw.strip()
    if not stripped:
        raise UnknownStructureError(f"SIA no confirmó el valor ni una ausencia para {label}")
    value: str | float = parse_decimal(stripped) if numeric else stripped
    return OfficialValue(
        status=Availability.AVAILABLE,
        provenance=provenance,
        value=value,
        unit=unit,
    )


def parse_adf_partial_response(xml: str) -> dict[str, str]:
    if len(xml) > MAX_ADF_CHARACTERS:
        raise UnknownStructureError("Respuesta ADF excede el límite seguro")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise UnknownStructureError("Respuesta parcial ADF inválida") from exc
    if root.tag != "partial-response":
        raise UnknownStructureError("La respuesta no es un partial-response de ADF")
    updates: dict[str, str] = {}
    for update in root.findall("./changes/update"):
        update_id = update.attrib.get("id")
        if not update_id or update_id in updates:
            raise UnknownStructureError("Actualización ADF sin ID único")
        updates[update_id] = update.text or ""
    if not updates:
        raise UnknownStructureError("Respuesta ADF sin actualizaciones")
    return updates


@dataclass(frozen=True, slots=True)
class TableSpec:
    structure_id: str
    section: str
    required_columns: dict[str, frozenset[str]]


COURSES_SPEC = TableSpec(
    structure_id="sia-history-courses-v1",
    section="Asignaturas",
    required_columns={
        "assignment": frozenset({"asignaturas", "asignatura"}),
        "credits": frozenset({"creditos"}),
        "type": frozenset({"tipo"}),
        "period": frozenset({"periodo", "periodo academico"}),
        "grade": frozenset({"calificacion", "nota"}),
    },
)

CREDIT_SUMMARY_SPEC = TableSpec(
    structure_id="sia-credit-typologies-v1",
    section="Tipologías",
    required_columns={
        "typology": frozenset({"tipologias", "tipologia"}),
        "required": frozenset({"exigidos"}),
        "passed": frozenset({"aprobados"}),
        "pending": frozenset({"pendientes"}),
        "enrolled": frozenset({"inscritos"}),
        "taken": frozenset({"cursados"}),
    },
)


def split_assignment(raw: str) -> tuple[str, str]:
    match = re.fullmatch(r"\s*(.*?)\s*\(([A-Za-z0-9][A-Za-z0-9.-]*)\)\s*", raw)
    if match is None or not match.group(1).strip():
        raise UnknownStructureError(f"Asignatura sin código reconocible: {raw!r}")
    return match.group(1).strip(), match.group(2)


def find_recognized_table(html: str, spec: TableSpec) -> tuple[list[str], list[dict[str, str]]]:
    soup = _parse_html(html)
    candidates: list[tuple[list[str], list[dict[str, str]]]] = []
    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue
        headers = [cell.get_text(" ", strip=True) for cell in table.find_all("th")]
        normalized = [normalize_label(header) for header in headers]
        mapping: dict[str, int] = {}
        for field, aliases in spec.required_columns.items():
            matches = [index for index, header in enumerate(normalized) if header in aliases]
            if len(matches) != 1:
                break
            mapping[field] = matches[0]
        if len(mapping) != len(spec.required_columns):
            continue
        rows: list[dict[str, str]] = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            if len(cells) != len(headers):
                raise UnknownStructureError("Fila con número inesperado de columnas")
            rows.append(
                {field: cells[index].get_text(" ", strip=True) for field, index in mapping.items()}
            )
        candidates.append((headers, rows))
    if len(candidates) != 1:
        raise UnknownStructureError(
            f"Se esperó una tabla reconocida para {spec.section}; se encontraron {len(candidates)}"
        )
    return candidates[0]


def detect_explicit_empty(html: str) -> Availability | None:
    soup = _parse_html(html)
    for text in soup.stripped_strings:
        status = EXPLICIT_ABSENCES.get(normalize_label(text))
        if status is not None:
            return status
    return None


def recognized_indicator(label: str) -> tuple[str, str | None]:
    normalized = normalize_label(label)
    normalized = re.sub(r"\s*\((papa|pappi)\)\s*$", "", normalized)
    if normalized not in KNOWN_INDICATORS:
        raise UnknownStructureError(f"Indicador oficial no reconocido: {label}")
    return KNOWN_INDICATORS[normalized]


def all_text_pairs(html: str) -> Iterable[tuple[str, str]]:
    """Extrae pares label/valor de filas de dos celdas o listas de definición."""

    soup = _parse_html(html)
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) == 2:
            yield cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True)
    terms = soup.find_all("dt")
    for term in terms:
        value = term.find_next_sibling("dd")
        if value is not None:
            yield term.get_text(" ", strip=True), value.get_text(" ", strip=True)
