"""文件功能：从 Codeflaws 数据集中筛选项目，并默认导入每个项目的第一个 C 文件。"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


FOLDER_PATTERN = re.compile(r"^.+-bug-\d+-\d+$")


@dataclass(frozen=True)
class ImportedCodeflawsProject:
    source_folder: Path
    project_folder: Path
    selected_source: Path


class CodeflawsImporter:
    """创建最小项目，只读取按文件名排序后的第一个 C 源文件。"""

    def __init__(self, dataset_root: str | Path, destination_root: str | Path):
        self.dataset_root = Path(dataset_root).resolve()
        self.destination_root = Path(destination_root).resolve()

    def discover(self) -> list[Path]:
        """仅返回符合 Codeflaws 缺陷对命名规则的目录。"""
        if not self.dataset_root.is_dir():
            raise FileNotFoundError(f"Codeflaws dataset does not exist: {self.dataset_root}")
        return sorted(
            (path for path in self.dataset_root.iterdir()
             if path.is_dir() and FOLDER_PATTERN.fullmatch(path.name)),
            key=lambda path: path.name,
        )

    def import_first(self, limit: int, offset: int = 0) -> list[ImportedCodeflawsProject]:
        """按固定排序导入指定范围的任务目录。"""
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset must be non-negative")
        selected = self.discover()[offset:offset + limit]
        imported = []
        for source_folder in selected:
            imported.append(self.import_one(source_folder))
        return imported

    def import_one(self, source_folder: str | Path) -> ImportedCodeflawsProject:
        """将排序后的第一个 C 源文件和英文需求复制到最小项目中。"""
        source_folder = Path(source_folder).resolve()
        try:
            source_folder.relative_to(self.dataset_root)
        except ValueError as exc:
            raise ValueError(f"Task is outside the Codeflaws root: {source_folder}") from exc
        if not FOLDER_PATTERN.fullmatch(source_folder.name):
            raise ValueError(f"Invalid Codeflaws folder name: {source_folder.name}")
        # 不根据目录名中的两个编号判断源码身份。目录内的 C 文件按名称排序，
        # 当前默认选择第一个；其余 C 文件不会被读取或复制。
        source_candidates = sorted(
            (path for path in source_folder.iterdir()
             if path.is_file() and path.suffix.lower() == ".c"),
            key=lambda path: path.name.casefold(),
        )
        if not source_candidates:
            raise FileNotFoundError(f"No C source file found in: {source_folder}")
        selected_source = source_candidates[0]
        selected_name = selected_source.name
        requirement_json = source_folder / "problem-description-en.json"
        if not requirement_json.is_file():
            raise FileNotFoundError(f"Requirement JSON is missing: {requirement_json}")
        requirement_data = json.loads(requirement_json.read_text(encoding="utf-8"))
        description = str(requirement_data.get("description_en", "")).strip()
        if not description:
            raise ValueError(f"description_en is empty: {requirement_json}")

        project_folder = self.destination_root / source_folder.name
        source_dir = project_folder / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected_source, source_dir / selected_name)
        (project_folder / "requirements.md").write_text(description + "\n", encoding="utf-8")
        # direct_main 使用进程内调用：执行器在编译时重命名被测程序的 main，
        # 再将被测目标文件与测试代码链接到同一个可执行文件中。
        manifest = {
            "project_id": source_folder.name,
            "source_files": [f"source/{selected_name}"],
            "include_dirs": [],
            "requirements_file": "requirements.md",
            "test_style": "direct_main",
            "compiler": {
                "standard": "gnu11",
                "flags": ["-Wall", "-Wextra", "-O0", "-g"],
                "link_flags": ["-lm"],
            },
        }
        (project_folder / "project.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return ImportedCodeflawsProject(source_folder, project_folder, selected_source)
