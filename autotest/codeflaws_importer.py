from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml


FOLDER_PATTERN = re.compile(r"^(?P<prefix>.+)-bug-(?P<buggy>\d+)-(?P<accepted>\d+)$")


@dataclass(frozen=True)
class ImportedCodeflawsProject:
    source_folder: Path
    project_folder: Path
    buggy_source: Path


class CodeflawsImporter:
    """Create minimal projects without reading accepted solutions or benchmark answers."""

    def __init__(self, dataset_root: str | Path, destination_root: str | Path):
        self.dataset_root = Path(dataset_root).resolve()
        self.destination_root = Path(destination_root).resolve()

    def discover(self) -> list[Path]:
        if not self.dataset_root.is_dir():
            raise FileNotFoundError(f"Codeflaws dataset does not exist: {self.dataset_root}")
        return sorted(
            (path for path in self.dataset_root.iterdir()
             if path.is_dir() and FOLDER_PATTERN.fullmatch(path.name)),
            key=lambda path: path.name,
        )

    def import_first(self, limit: int, offset: int = 0) -> list[ImportedCodeflawsProject]:
        if limit < 1 or offset < 0:
            raise ValueError("limit must be positive and offset must be non-negative")
        selected = self.discover()[offset:offset + limit]
        imported = []
        for source_folder in selected:
            imported.append(self.import_one(source_folder))
        return imported

    def import_one(self, source_folder: str | Path) -> ImportedCodeflawsProject:
        source_folder = Path(source_folder).resolve()
        try:
            source_folder.relative_to(self.dataset_root)
        except ValueError as exc:
            raise ValueError(f"Task is outside the Codeflaws root: {source_folder}") from exc
        match = FOLDER_PATTERN.fullmatch(source_folder.name)
        if not match:
            raise ValueError(f"Invalid Codeflaws folder name: {source_folder.name}")
        buggy_name = f"{match.group('prefix')}-{match.group('buggy')}.c"
        buggy_source = source_folder / buggy_name
        requirement_json = source_folder / "problem-description-en.json"
        if not buggy_source.is_file():
            raise FileNotFoundError(f"Buggy source is missing: {buggy_source}")
        if not requirement_json.is_file():
            raise FileNotFoundError(f"Requirement JSON is missing: {requirement_json}")
        requirement_data = json.loads(requirement_json.read_text(encoding="utf-8"))
        description = str(requirement_data.get("description_en", "")).strip()
        if not description:
            raise ValueError(f"description_en is empty: {requirement_json}")

        project_folder = self.destination_root / source_folder.name
        source_dir = project_folder / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(buggy_source, source_dir / buggy_name)
        (project_folder / "requirements.md").write_text(description + "\n", encoding="utf-8")
        manifest = {
            "project_id": source_folder.name,
            "source_files": [f"source/{buggy_name}"],
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
        return ImportedCodeflawsProject(source_folder, project_folder, buggy_source)
