"""Validación fail-closed del manifiesto de completitud."""

from __future__ import annotations

from .models import AcademicRecord, Availability, ValidationIssue, ValidationReport
from .parsing import KNOWN_INDICATORS, normalize_label
from .security import NavigationDenied, NavigationPolicy

REQUIRED_SECTIONS = frozenset(
    {"Estudiante", "Asignaturas", "Periodos académicos", "Tipologías", "Indicadores"}
)


def validate(record: AcademicRecord) -> ValidationReport:
    issues: list[ValidationIssue] = []
    missing = REQUIRED_SECTIONS.difference(record.evidence)
    for section in sorted(missing):
        issues.append(ValidationIssue("missing_section", "No existe evidencia de carga", section))

    for section, evidence in record.evidence.items():
        try:
            NavigationPolicy.assert_academic_source(evidence.source_url)
        except NavigationDenied as exc:
            issues.append(ValidationIssue("invalid_source", str(exc), section))
        if not evidence.recognized:
            issues.append(ValidationIssue("unknown_structure", "Estructura no reconocida", section))
        if evidence.pages_visited < 1:
            issues.append(ValidationIssue("no_pages", "No se confirmó ninguna página", section))
        if not evidence.pagination_complete:
            issues.append(ValidationIssue("incomplete_pagination", "No se probó el fin", section))
        if evidence.record_count == 0 and evidence.explicit_empty_status is None:
            issues.append(
                ValidationIssue(
                    "ambiguous_empty",
                    "No hay registros ni una ausencia explícita de SIA",
                    section,
                )
            )
        if evidence.record_count > 0 and evidence.explicit_empty_status is not None:
            issues.append(
                ValidationIssue(
                    "conflicting_empty",
                    "La sección contiene registros y una ausencia oficial",
                    section,
                )
            )

    known_names = {canonical for canonical, _ in KNOWN_INDICATORS.values()}
    for indicator in record.indicators:
        if indicator.canonical_name not in known_names:
            issues.append(
                ValidationIssue(
                    "unknown_indicator",
                    f"Indicador no reconocido: {indicator.canonical_name}",
                    "Indicadores",
                )
            )
        value = indicator.official_value
        if value.status is not Availability.AVAILABLE and normalize_label(
            str(value.display_value)
        ) not in {
            normalize_label(item.value)
            for item in Availability
            if item is not Availability.AVAILABLE
        }:
            issues.append(
                ValidationIssue("invalid_absence", "Ausencia oficial no reconocida", "Indicadores")
            )

    period_field_sets = {frozenset(period.fields) for period in record.periods}
    if len(period_field_sets) > 1:
        issues.append(
            ValidationIssue(
                "inconsistent_period_fields",
                "Los periodos no tienen el mismo conjunto de campos",
                "Periodos académicos",
            )
        )

    return ValidationReport(valid=not issues, issues=tuple(issues))
