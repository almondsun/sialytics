"""Adaptador Playwright para una sesión interactiva de SIA."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from .models import (
    AcademicPeriod,
    AcademicRecord,
    CourseAttempt,
    CreditSummary,
    Indicator,
    OfficialValue,
    Program,
    SectionEvidence,
    Student,
)
from .parsing import (
    COURSES_SPEC,
    CREDIT_SUMMARY_SPEC,
    TableSpec,
    UnknownStructureError,
    normalize_label,
    official_value,
    parse_course_grade,
    recognized_indicator,
    split_assignment,
)
from .security import SIA_HOST, NavigationDenied, NavigationPolicy

SIA_START_URL = "https://sia.unal.edu.co/ServiciosApp/faces/inicioServicios"


@dataclass(frozen=True, slots=True)
class SiaPageProfile:
    academic_menu: str = "Información académica"
    history_link: str = "Mi historia académica"
    indicator_labels: tuple[str, ...] = (
        "Pregrado - Promedio académico",
        "Porcentaje de Avance",
        "Cupo de créditos",
    )


class SiaExtractor:
    """Sesión efímera; nunca recibe ni persiste credenciales."""

    def __init__(
        self,
        policy: NavigationPolicy | None = None,
        profile: SiaPageProfile | None = None,
    ) -> None:
        self.policy = policy or NavigationPolicy.from_environment()
        self.profile = profile or SiaPageProfile()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def __aenter__(self) -> SiaExtractor:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context(accept_downloads=False)
        await self._context.route("**/*", self._route_request)
        self._page = await self._context.new_page()
        self._context.on("page", self._handle_popup)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    async def _route_request(self, route: Any) -> None:
        request = route.request
        if request.resource_type == "document":
            try:
                self.policy.assert_navigation_url(request.url)
            except NavigationDenied:
                await route.abort("blockedbyclient")
                return
        await route.continue_()

    def _handle_popup(self, page: Page) -> None:
        async def inspect() -> None:
            await page.wait_for_load_state("domcontentloaded")
            try:
                self.policy.assert_navigation_url(page.url)
            except NavigationDenied:
                await page.close()

        asyncio.create_task(inspect())

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Use SiaExtractor como administrador de contexto asíncrono")
        return self._page

    async def authenticate_and_list_programs(self) -> list[Program]:
        await self.page.goto(SIA_START_URL, wait_until="domcontentloaded")
        for _ in range(600):
            if self.page.url.split("/", 3)[2].lower() == SIA_HOST:
                menu = self.page.get_by_text(self.profile.academic_menu, exact=True)
                if any([await menu.nth(index).is_visible() for index in range(await menu.count())]):
                    break
            await self.page.wait_for_timeout(500)
        else:
            raise TimeoutError("SIA no confirmó la autenticación en cinco minutos")
        self.policy.assert_navigation_url(self.page.url)
        if self.page.url.split("/", 3)[2].lower() != SIA_HOST:
            raise NavigationDenied("La sesión autenticada no regresó a sia.unal.edu.co")

        await self._click_visible_exact(self.profile.academic_menu)
        await self._click_visible_exact(self.profile.history_link)
        await self.page.wait_for_timeout(2_000)
        NavigationPolicy.assert_academic_source(self.page.url)

        selects = self.page.locator("select")
        for index in range(await selects.count()):
            select = selects.nth(index)
            descriptor = await select.evaluate(
                """el => [
                    el.getAttribute('aria-label'), el.getAttribute('title'),
                    el.getAttribute('name'), el.id,
                    ...Array.from(el.labels || []).map(label => label.textContent)
                ].filter(Boolean).join(' ')"""
            )
            normalized_descriptor = str(descriptor).lower()
            if "program" in normalized_descriptor or "plan de estudio" in normalized_descriptor:
                options = await select.locator("option").evaluate_all(
                    "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))"
                )
                return [
                    Program(
                        str(option["value"]),
                        str(option["text"]),
                        str(option["text"]),
                    )
                    for option in options
                    if str(option["value"]).strip() and str(option["text"]).strip()
                ]
        raise UnknownStructureError("No se pudo reconocer el selector de programa académico")

    async def _click_visible_exact(self, text: str) -> None:
        matches = self.page.get_by_text(text, exact=True)
        visible = [
            matches.nth(index)
            for index in range(await matches.count())
            if await matches.nth(index).is_visible()
        ]
        if len(visible) != 1:
            raise UnknownStructureError(
                f"Se esperaba un control visible llamado {text!r}; se encontraron {len(visible)}"
            )
        await visible[0].click()
        await self.page.wait_for_timeout(1_000)

    async def _select_program(self, program: Program) -> None:
        selects = self.page.locator("select")
        for index in range(await selects.count()):
            select = selects.nth(index)
            options = await select.locator("option").evaluate_all("els => els.map(e => e.value)")
            if program.program_id in {str(value) for value in options}:
                await select.select_option(program.program_id)
                await self.page.wait_for_timeout(2_000)
                return
        raise UnknownStructureError("El selector de programa cambió después de autenticar")

    async def _assert_no_unhandled_pagination(self) -> None:
        candidates = self.page.locator(
            "[aria-label='Siguiente' i], [title='Siguiente' i], "
            "button:has-text('Siguiente'), a:has-text('Siguiente')"
        )
        for index in range(await candidates.count()):
            candidate = candidates.nth(index)
            if await candidate.is_visible() and await candidate.is_enabled():
                if await candidate.get_attribute("aria-disabled") != "true":
                    raise UnknownStructureError(
                        "La tabla presenta paginación no recorrida; no se puede probar completitud"
                    )

    async def _extract_rendered_table(
        self, spec: TableSpec
    ) -> tuple[list[str], list[dict[str, str]]]:
        row_locators = self.page.locator("tr")
        candidates: list[tuple[Any, list[str], dict[str, int]]] = []
        for index in range(await row_locators.count()):
            row = row_locators.nth(index)
            if not await row.is_visible():
                continue
            cells = [
                text.strip()
                for text in await row.locator(":scope > th, :scope > td").all_text_contents()
            ]
            normalized = [normalize_label(cell) for cell in cells]
            mapping: dict[str, int] = {}
            for field, aliases in spec.required_columns.items():
                matches = [i for i, header in enumerate(normalized) if header in aliases]
                if len(matches) != 1:
                    break
                mapping[field] = matches[0]
            if len(mapping) == len(spec.required_columns):
                candidates.append((row, cells, mapping))
        if len(candidates) != 1:
            raise UnknownStructureError(
                f"Se esperaba un encabezado reconocido para {spec.section}; "
                f"se encontraron {len(candidates)}"
            )

        header_row, headers, mapping = candidates[0]
        rendered_rows = await header_row.evaluate(
            """(header, width) => {
                for (let root = header.parentElement; root; root = root.parentElement) {
                    const rows = Array.from(root.querySelectorAll('tr')).filter(row =>
                        row.getClientRects().length > 0 &&
                        Array.from(row.children).filter(cell =>
                            cell.tagName === 'TD' || cell.tagName === 'TH'
                        ).length === width
                    );
                    const materialRows = rows.filter(row => row !== header &&
                        Array.from(row.children).some(cell => cell.innerText.trim()));
                    if (materialRows.length > 0) {
                        return rows.map(row => Array.from(row.children)
                            .filter(cell => cell.tagName === 'TD' || cell.tagName === 'TH')
                            .map(cell => cell.innerText.trim()));
                    }
                }
                return [];
            }""",
            len(headers),
        )
        normalized_headers = [normalize_label(header) for header in headers]
        data: list[dict[str, str]] = []
        for raw_row in rendered_rows:
            if [normalize_label(str(cell)) for cell in raw_row] == normalized_headers:
                continue
            if len(raw_row) != len(headers):
                raise UnknownStructureError("Fila renderizada con ancho inesperado")
            if not any(str(cell).strip() for cell in raw_row):
                continue
            data.append(
                {field: str(raw_row[position]).strip() for field, position in mapping.items()}
            )
        if not data:
            raise UnknownStructureError(f"{spec.section} no contiene filas renderizadas")
        return headers, data

    async def _read_indicator(self, label: str) -> str:
        matches = self.page.get_by_text(label, exact=True)
        values: set[str] = set()
        for index in range(await matches.count()):
            node = matches.nth(index)
            if not await node.is_visible():
                continue
            value = await node.evaluate(
                r"""(labelNode, label) => {
                    const normalizedLabel = label.trim();
                    for (let root = labelNode.parentElement, depth = 0;
                         root && depth < 5;
                         root = root.parentElement, depth++) {
                        const text = root.innerText.replace(normalizedLabel, ' ');
                        const absences = text.match(
                            /No disponible|Sin información registrada/gi
                        ) || [];
                        const numbers = text.match(/(?:^|\s)(\d+(?:[.,]\d+)?\s*%?)(?=\s|$)/g) || [];
                        const candidates = [...absences, ...numbers].map(v => v.trim());
                        if (candidates.length === 1) return candidates[0];
                    }
                    return null;
                }""",
                label,
            )
            if value:
                values.add(str(value))
        if len(values) != 1:
            raise UnknownStructureError(
                f"No se obtuvo un valor único para el indicador oficial {label!r}"
            )
        return values.pop()

    async def extract(self, program_id: str) -> AcademicRecord:
        programs = await self.authenticate_and_list_programs()
        matches = [program for program in programs if program.program_id == program_id]
        if len(matches) != 1:
            raise ValueError("Seleccione exactamente uno de los programas detectados")
        return await self.extract_authenticated(matches[0])

    async def extract_authenticated(self, program: Program) -> AcademicRecord:
        await self._select_program(program)
        now = datetime.now(UTC)
        source_url = self.page.url
        NavigationPolicy.assert_academic_source(source_url)
        await self._assert_no_unhandled_pagination()

        student_fields = {
            "Plan de estudios": official_value(
                program.study_plan or program.name,
                source_url=source_url,
                section="Estudiante",
                label="Plan de estudios",
                observed_at=now,
            )
        }

        course_headers, course_rows = await self._extract_rendered_table(COURSES_SPEC)
        courses: list[CourseAttempt] = []

        def course_value(raw: str, label: str, *, numeric: bool = False) -> OfficialValue:
            return official_value(
                raw,
                source_url=source_url,
                section="Asignaturas",
                label=label,
                numeric=numeric,
                observed_at=now,
            )

        for row in course_rows:
            course_name, course_code = split_assignment(row["assignment"])
            grade, result = parse_course_grade(row["grade"])
            grade_value = str(grade) if grade is not None else row["grade"]
            extra_fields = (
                {"Resultado": course_value(result, "Resultado")} if result is not None else {}
            )
            courses.append(
                CourseAttempt(
                    period=course_value(row["period"], "Periodo"),
                    code=course_value(course_code, "Código de asignatura"),
                    name=course_value(course_name, "Asignaturas"),
                    credits=course_value(row["credits"], "Créditos", numeric=True),
                    grade=course_value(grade_value, "Calificación", numeric=grade is not None),
                    course_type=course_value(row["type"], "Tipo"),
                    extra_fields=extra_fields,
                )
            )

        typology_headers, typology_rows = await self._extract_rendered_table(CREDIT_SUMMARY_SPEC)
        credit_summaries: list[CreditSummary] = []
        typology_labels = {
            "typology": "Tipologías",
            "required": "Exigidos",
            "passed": "Aprobados",
            "pending": "Pendientes",
            "enrolled": "Inscritos",
            "taken": "Cursados",
        }
        for row in typology_rows:
            values = {
                field: official_value(
                    row[field],
                    source_url=source_url,
                    section="Tipologías",
                    label=label,
                    numeric=field != "typology",
                    observed_at=now,
                )
                for field, label in typology_labels.items()
            }
            credit_summaries.append(
                CreditSummary(
                    values["typology"],
                    values["required"],
                    values["passed"],
                    values["pending"],
                    values["enrolled"],
                    values["taken"],
                )
            )

        indicators: list[Indicator] = []
        for label in self.profile.indicator_labels:
            raw_value = await self._read_indicator(label)
            canonical, acronym = recognized_indicator(label)
            numeric = any(character.isdigit() for character in raw_value)
            cleaned_value = raw_value.replace("%", "").strip() if numeric else raw_value
            indicators.append(
                Indicator(
                    canonical,
                    acronym,
                    official_value(
                        cleaned_value,
                        source_url=source_url,
                        section="Indicadores",
                        label=label,
                        numeric=numeric,
                        unit="%" if "%" in raw_value else None,
                        observed_at=now,
                    ),
                )
            )

        periods = _derive_periods(courses)
        evidence = {
            "Estudiante": SectionEvidence(
                "Estudiante",
                "sia-study-plan-v1",
                source_url,
                True,
                tuple(student_fields),
                1,
                True,
                len(student_fields),
            ),
            "Asignaturas": SectionEvidence(
                "Asignaturas",
                COURSES_SPEC.structure_id,
                source_url,
                True,
                tuple(course_headers),
                1,
                True,
                len(courses),
            ),
            "Periodos académicos": SectionEvidence(
                "Periodos académicos",
                "sialytics-periods-v1",
                source_url,
                True,
                ("Periodo académico",),
                1,
                True,
                len(periods),
            ),
            "Tipologías": SectionEvidence(
                "Tipologías",
                CREDIT_SUMMARY_SPEC.structure_id,
                source_url,
                True,
                tuple(typology_headers),
                1,
                True,
                len(credit_summaries),
            ),
            "Indicadores": SectionEvidence(
                "Indicadores",
                "sia-history-indicators-v1",
                source_url,
                True,
                tuple(item.canonical_name for item in indicators),
                1,
                True,
                len(indicators),
            ),
        }
        return AcademicRecord(
            student=Student(program, student_fields),
            courses=courses,
            periods=periods,
            indicators=indicators,
            evidence=evidence,
            extracted_at=now,
            credit_summaries=credit_summaries,
        )


def _derive_periods(courses: list[CourseAttempt]) -> list[AcademicPeriod]:
    """Agregación inequívoca y explícitamente no institucional."""

    grouped: dict[str, float] = {}
    for course in courses:
        if not isinstance(course.period.value, str) or not isinstance(course.credits.value, float):
            continue
        grouped[course.period.value] = grouped.get(course.period.value, 0.0) + course.credits.value
    periods: list[AcademicPeriod] = []
    for name, credits in sorted(grouped.items()):
        provenance = course_provenance(courses, name)
        periods.append(
            AcademicPeriod(
                name,
                {
                    "Créditos registrados (Calculado por SIAlytics)": official_value(
                        str(credits),
                        source_url=provenance,
                        section="Periodos académicos",
                        label="Calculado por SIAlytics",
                        numeric=True,
                    )
                },
            )
        )
    return periods


def course_provenance(courses: list[CourseAttempt], period: str) -> str:
    for course in courses:
        if course.period.value == period:
            return course.period.provenance.source_url
    raise AssertionError("El periodo fue derivado de una asignatura inexistente")
