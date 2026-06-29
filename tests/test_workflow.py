from pathlib import Path

from sialytics.workflow import _resolve_output_directory


def test_default_output_is_anchored_to_project_root(tmp_path: Path, monkeypatch: object) -> None:
    project = tmp_path / "project"
    notebooks = project / "notebooks"
    notebooks.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname = 'sialytics'\n")
    monkeypatch.chdir(notebooks)  # type: ignore[attr-defined]

    assert _resolve_output_directory(None) == project / "outputs"


def test_relative_custom_output_is_also_project_anchored(
    tmp_path: Path, monkeypatch: object
) -> None:
    project = tmp_path / "project"
    notebooks = project / "notebooks"
    notebooks.mkdir(parents=True)
    (project / "pyproject.toml").write_text("[project]\nname = 'sialytics'\n")
    monkeypatch.chdir(notebooks)  # type: ignore[attr-defined]

    assert _resolve_output_directory("reports") == project / "reports"
