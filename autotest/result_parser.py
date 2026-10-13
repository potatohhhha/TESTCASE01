"""文件功能：解析任务状态、JUnit XML 和日志，生成统一的测试结果。"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

VALID = {"PASSED", "FAILED", "BUILD_FAILED", "TIMEOUT", "CRASHED", "GENERATION_FAILED", "INFRA_ERROR"}


class ResultParser:
    def parse(self, output_dir: str | Path) -> dict[str, Any]:
        """合并执行状态、生成元数据、JUnit XML 和文本日志。"""
        output = Path(output_dir)
        result_file = output / "result.json"
        raw = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {
            "status": "INFRA_ERROR", "error": "result.json is missing", "duration_seconds": 0}
        if raw.get("status") not in VALID:
            raw["status"], raw["error"] = "INFRA_ERROR", f"Unknown status: {raw.get('status')}"
        metadata_file = output / "testcases.json"
        metadata = json.loads(metadata_file.read_text(encoding="utf-8")) if metadata_file.exists() else {"testcases": []}
        xml_states: dict[str, tuple[str, str]] = {}
        xml_file = output / "test-results.xml"
        # CMocka 函数名可能在用例 ID 外增加前后缀，因此按“名称包含 ID”关联
        # 元数据，而不要求与 XML 中的名称完全相同。
        if xml_file.exists():
            try:
                for case in ET.parse(xml_file).iterfind(".//testcase"):
                    name = case.get("name", "")
                    child = case.find("failure")
                    if child is None:
                        child = case.find("error")
                    if child is None:
                        child = case.find("skipped")
                    state = "PASSED" if child is None else ("NOT_RUN" if child.tag == "skipped" else "FAILED")
                    xml_states[name] = (state, "" if child is None else (child.get("message") or child.text or ""))
            except ET.ParseError as exc:
                raw["xml_error"] = str(exc)
        elif raw["status"] in {"PASSED", "FAILED"}:
            raw["status"] = "INFRA_ERROR"
            raw["error"] = "test-results.xml is missing"
        cases = []
        runnable = raw["status"] in {"PASSED", "FAILED"}
        for case in metadata.get("testcases", []):
            match = next((value for name, value in xml_states.items() if case["testcase_id"] in name), None)
            state, detail = match if match else (("NOT_RUN", "No JUnit result") if runnable else ("NOT_RUN", raw["status"]))
            cases.append({**case, "actual_status": state, "actual_detail": detail})
        raw["testcases"] = cases
        raw["counts"] = {key: sum(c["actual_status"] == key for c in cases) for key in ("PASSED", "FAILED", "NOT_RUN")}
        raw["build_log"] = self._read(output / "build.log")
        raw["execution_log"] = self._read(output / "execution.log")
        return raw

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

