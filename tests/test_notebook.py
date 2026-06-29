import json
from pathlib import Path


def test_notebook_contract() -> None:
    notebook = json.loads(Path("notebooks/sialytics.ipynb").read_text())
    assert notebook["nbformat"] == 4
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert all(cell["execution_count"] is None for cell in code_cells)
    assert all(not cell["outputs"] for cell in code_cells)
    content = json.dumps(notebook, ensure_ascii=False).lower()
    assert "gpa" not in content


def test_user_documentation_uses_unal_terms() -> None:
    readme = " ".join(Path("README.md").read_text().lower().split())
    assert "papa" in readme
    assert "pappi" in readme
    assert "avance curricular" in readme
    assert "gpa" not in readme
