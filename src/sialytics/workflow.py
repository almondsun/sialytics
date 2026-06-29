"""Orquestación pequeña para el notebook."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from .export import export_xlsx
from .security import NavigationPolicy
from .sia import SiaExtractor


def _project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return current


def _resolve_output_directory(output_directory: str | Path | None) -> Path:
    project_root = _project_root()
    if output_directory is None:
        return project_root / "outputs"
    configured = Path(output_directory).expanduser()
    return configured if configured.is_absolute() else project_root / configured


async def run_interactive(output_directory: str | Path | None = None) -> Path:
    async with SiaExtractor(NavigationPolicy.from_environment()) as extractor:
        programs = await extractor.authenticate_and_list_programs()
        for index, program in enumerate(programs, start=1):
            print(f"{index}. {program.name}")
        raw_selection = await asyncio.to_thread(input, "Seleccione un programa: ")
        selection = int(raw_selection) - 1
        if selection < 0 or selection >= len(programs):
            raise ValueError("Selección de programa inválida")
        record = await extractor.extract_authenticated(programs[selection])
    filename = f"sialytics-{datetime.now().astimezone():%Y%m%d-%H%M%S}.xlsx"
    return export_xlsx(record, _resolve_output_directory(output_directory) / filename)
