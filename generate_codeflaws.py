from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from autotest.codeflaws_importer import CodeflawsImporter
from autotest.project_loader import ProjectLoader
from autotest.testcase_generator import TestCaseGenerator

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely import and generate tests for selected Codeflaws tasks")
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true", help="Import only; do not call the LLM")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")

    importer = CodeflawsImporter(args.dataset_root, ROOT / "inputs" / "codeflaws")
    imported = importer.import_first(args.limit, args.offset)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = ROOT / "workspace" / "codeflaws-generation" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    loader = ProjectLoader()
    generator = TestCaseGenerator(ROOT / "prompts" / "testcase_generation.md", max_attempts=3)
    summary = []
    for item in imported:
        record = {"project_id": item.project_folder.name, "status": "IMPORTED"}
        if not args.dry_run:
            try:
                project = loader.load(item.project_folder)
                generated = generator.generate(project, run_dir / project.project_id, mock=False)
                record.update(status="GENERATED", testcase_count=len(generated.testcases))
            except Exception as exc:
                record.update(status="GENERATION_FAILED", error=str(exc))
        summary.append(record)
        print(f"{record['project_id']}: {record['status']}")
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {run_dir}")
    return 0 if all(item["status"] in {"IMPORTED", "GENERATED"} for item in summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())
