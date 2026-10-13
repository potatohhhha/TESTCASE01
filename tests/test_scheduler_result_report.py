"""文件功能：验证任务调度、结果解析以及 HTML 报告生成。"""

import json
import time
from pathlib import Path

from autotest.docker_runner import RunnerResult
from autotest.report_generator import ReportGenerator
from autotest.result_parser import ResultParser
from autotest.task_builder import Task
from autotest.task_scheduler import TaskScheduler


class FakeRunner:
    def run(self, task):
        time.sleep(0.05)
        return RunnerResult(task, "PASSED")

    def _infra_result(self, task, status, message):
        raise AssertionError(message)


def make_task(tmp_path: Path, number: int) -> Task:
    paths = [tmp_path / f"{number}-{x}" for x in ("in", "out", "build")]
    for path in paths:
        path.mkdir()
    return Task("run", f"task-{number}", f"project-{number}", *paths)


def test_scheduler_collects_four_tasks(workdir: Path):
    results = TaskScheduler(FakeRunner(), workers=4).run([make_task(workdir, x) for x in range(4)])
    assert len(results) == 4
    assert all(result.status == "PASSED" for result in results)


def test_result_parser_and_html(workdir: Path):
    (workdir / "result.json").write_text('{"status":"BUILD_FAILED","duration_seconds":0.2}', encoding="utf-8")
    (workdir / "testcases.json").write_text(json.dumps({"testcases": [{"testcase_id": "TC001",
        "requirement_id": "REQ001", "description": "case", "inputs": {}, "expected": {}}]}), encoding="utf-8")
    parsed = ResultParser().parse(workdir)
    assert parsed["counts"]["NOT_RUN"] == 1
    assert parsed["status"] == "BUILD_FAILED"
    project = type("P", (), {"project_id": "example", "source_files": ["limit.c"]})()
    report = ReportGenerator().project_report(project, parsed, workdir)
    assert "BUILD_FAILED" in report.read_text(encoding="utf-8")

