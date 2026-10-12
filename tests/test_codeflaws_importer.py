import json
from pathlib import Path

from autotest.codeflaws_importer import CodeflawsImporter
from autotest.project_loader import ProjectLoader


def test_imports_only_buggy_source_and_description(workdir: Path):
    dataset = workdir / "dataset"
    task = dataset / "1-A-bug-100-200"
    task.mkdir(parents=True)
    (task / "1-A-100.c").write_text("int main(void) { return 1; }", encoding="utf-8")
    (task / "1-A-200.c").write_text("ACCEPTED_SOLUTION_SENTINEL", encoding="utf-8")
    (task / "output-pos1").write_text("SECRET_EXPECTED_OUTPUT", encoding="utf-8")
    (task / "problem-description-en.json").write_text(
        json.dumps({"description_en": "Only this requirement is imported."}), encoding="utf-8")

    imported = CodeflawsImporter(dataset, workdir / "inputs").import_first(1)
    destination = imported[0].project_folder
    copied_sources = list((destination / "source").glob("*.c"))
    assert [path.name for path in copied_sources] == ["1-A-100.c"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in destination.rglob("*.*"))
    assert "ACCEPTED_SOLUTION_SENTINEL" not in combined
    assert "SECRET_EXPECTED_OUTPUT" not in combined
    assert "Only this requirement is imported." in combined
    project = ProjectLoader().load(destination)
    assert project.test_style == "direct_main"
    assert project.compiler["link_flags"] == ["-lm"]
