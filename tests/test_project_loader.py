from pathlib import Path

import pytest

from autotest.project_loader import ProjectLoader


ROOT = Path(__file__).parents[1]


def test_loads_example_project():
    project = ProjectLoader().load(ROOT / "inputs" / "project_a")
    assert project.project_id == "project_a"
    assert len(project.source_files) == 1
    assert len(project.header_files) == 1
    assert "REQ001" in project.requirements.text


def test_rejects_path_traversal(workdir: Path):
    (workdir / "requirements.md").write_text("valid", encoding="utf-8")
    (workdir / "project.yaml").write_text(
        "project_id: bad\nsource_files: [../outside.c]\nrequirements_file: requirements.md\n", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        ProjectLoader().load(workdir)

