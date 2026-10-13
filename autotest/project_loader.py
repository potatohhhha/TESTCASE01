"""文件功能：读取并校验项目清单，将项目文件解析为统一的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .document_loader import Document, DocumentLoader


@dataclass(frozen=True)
class Project:
    project_id: str
    root: Path
    source_files: list[Path]
    include_dirs: list[Path]
    header_files: list[Path]
    requirements: Document
    compiler: dict[str, Any]
    mock_profile: str = "pass"
    test_style: str = "function"


class ProjectLoader:
    def __init__(self, document_loader: DocumentLoader | None = None):
        self.documents = document_loader or DocumentLoader()

    @staticmethod
    def _inside(root: Path, relative: str, kind: str) -> Path:
        """解析清单中的路径，并拒绝越出项目根目录的路径。"""
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"{kind} escapes project directory: {relative}") from exc
        return candidate

    def load(self, project_dir: str | Path) -> Project:
        """校验 project.yaml，并返回解析后的可信项目路径。"""
        root = Path(project_dir).resolve()
        manifest = root / "project.yaml"
        if not manifest.is_file():
            raise FileNotFoundError(f"Project manifest does not exist: {manifest}")
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("project.yaml must contain a mapping")
        project_id = str(data.get("project_id", "")).strip()
        if not project_id:
            raise ValueError("project_id is required")
        sources = [self._inside(root, str(x), "source file") for x in data.get("source_files", [])]
        if not sources:
            raise ValueError("At least one source_files entry is required")
        for source in sources:
            if source.suffix.lower() != ".c" or not source.is_file():
                raise ValueError(f"C source file does not exist or is not .c: {source}")
        includes = [self._inside(root, str(x), "include directory") for x in data.get("include_dirs", [])]
        for include in includes:
            if not include.is_dir():
                raise ValueError(f"Include directory does not exist: {include}")
        # 头文件内容会发送给生成器，因此需解析符号链接，并执行与源码、
        # 需求文档相同的项目目录边界检查。
        headers = []
        for include in includes:
            for header in include.rglob("*.h"):
                resolved = header.resolve()
                try:
                    resolved.relative_to(root)
                except ValueError as exc:
                    raise ValueError(f"Header resolves outside project directory: {header}") from exc
                headers.append(resolved)
        headers = sorted(set(headers))
        requirement_path = self._inside(root, str(data.get("requirements_file", "")), "requirements file")
        compiler = data.get("compiler", {})
        standard = str(compiler.get("standard", "c11"))
        flags = [str(x) for x in compiler.get("flags", ["-Wall", "-Wextra", "-O0", "-g"])]
        link_flags = [str(x) for x in compiler.get("link_flags", [])]
        if not standard.replace("gnu", "").replace("c", "").isdigit():
            raise ValueError(f"Invalid C standard: {standard}")
        test_style = str(data.get("test_style", "function"))
        if test_style not in {"function", "console", "direct_main"}:
            raise ValueError(f"Unsupported test_style: {test_style}")
        return Project(project_id, root, sources, includes, headers,
                       self.documents.load(requirement_path),
                       {"standard": standard, "flags": flags, "link_flags": link_flags},
                       str(data.get("mock_profile", "pass")), test_style)

