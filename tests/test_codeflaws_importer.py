"""文件功能：验证 Codeflaws 导入器只导入排序后的第一个 C 文件和公开需求。"""

import json
from pathlib import Path

from autotest.codeflaws_importer import CodeflawsImporter
from autotest.project_loader import ProjectLoader


def test_imports_only_first_sorted_source_and_description(workdir: Path):
    dataset = workdir / "dataset"
    # 目录编号的顺序与文件名字典序相反，用于证明导入器没有依据目录名
    # 推断哪个文件有缺陷，而是单纯选择排序后的第一个 C 文件。
    task = dataset / "1-A-bug-200-100"
    task.mkdir(parents=True)
    (task / "1-A-200.c").write_text("UNSELECTED_SOURCE_SENTINEL", encoding="utf-8")
    (task / "1-A-100.c").write_text("int main(void) { return 1; }", encoding="utf-8")
    (task / "output-pos1").write_text("SECRET_EXPECTED_OUTPUT", encoding="utf-8")
    (task / "problem-description-en.json").write_text(
        json.dumps({"description_en": "Only this requirement is imported."}), encoding="utf-8")

    imported = CodeflawsImporter(dataset, workdir / "inputs").import_first(1)
    destination = imported[0].project_folder
    copied_sources = list((destination / "source").glob("*.c"))
    assert [path.name for path in copied_sources] == ["1-A-100.c"]
    assert imported[0].selected_source.name == "1-A-100.c"
    combined = "\n".join(path.read_text(encoding="utf-8") for path in destination.rglob("*.*"))
    assert "UNSELECTED_SOURCE_SENTINEL" not in combined
    assert "SECRET_EXPECTED_OUTPUT" not in combined
    assert "Only this requirement is imported." in combined
    project = ProjectLoader().load(destination)
    assert project.test_style == "direct_main"
    assert project.compiler["link_flags"] == ["-lm"]
