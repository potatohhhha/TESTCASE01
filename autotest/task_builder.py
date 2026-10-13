"""文件功能：为每个测试任务创建隔离的输入、构建和输出目录。"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .project_loader import Project


@dataclass(frozen=True)
class Task:
    run_id: str
    task_id: str
    project_id: str
    input_dir: Path
    output_dir: Path
    build_dir: Path


class TaskBuilder:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()

    def build(self, project: Project, generated_dir: str | Path, output_dir: str | Path,
              run_id: str, test_timeout_seconds: float = 5) -> Task:
        """为任务创建只读输入快照及可写的构建、输出目录。"""
        task_id = f"{project.project_id}-{uuid.uuid4().hex[:10]}"
        task_root = self.workspace_root / run_id / task_id
        input_dir, build_dir = task_root / "input", task_root / "build"
        output = Path(output_dir).resolve()
        for directory in (input_dir, build_dir, output):
            directory.mkdir(parents=True, exist_ok=False) if not directory.exists() else None
        # 容器只接收复制后的快照，不直接挂载原始项目目录；文件名前缀还可
        # 避免多个同名源文件发生冲突。
        source_names = []
        for index, source in enumerate(project.source_files):
            name = f"src_{index}_{source.name}"
            shutil.copy2(source, input_dir / name)
            source_names.append(name)
        include_names = []
        for index, include in enumerate(project.include_dirs):
            name = f"include_{index}"
            shutil.copytree(include, input_dir / name)
            include_names.append(name)
        generated = Path(generated_dir)
        shutil.copy2(generated / "test_generated.c", input_dir / "test_generated.c")
        config = {"source_files": source_names, "include_dirs": include_names,
                  "compiler": project.compiler, "test_style": project.test_style,
                  "test_timeout_seconds": test_timeout_seconds}
        (input_dir / "task.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        return Task(run_id, task_id, project.project_id, input_dir, output, build_dir)

