"""文件功能：提供环境检查、测试生成、Docker 执行和报告输出的命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import xml.etree.ElementTree as ET
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from autotest.docker_runner import DockerRunner
from autotest.project_loader import ProjectLoader
from autotest.report_generator import ReportGenerator
from autotest.result_parser import ResultParser
from autotest.task_builder import TaskBuilder
from autotest.task_scheduler import TaskScheduler
from autotest.testcase_generator import GeneratedTests, TestCaseGenerator

ROOT = Path(__file__).resolve().parent


def configuration() -> dict:
    """从仓库内的配置文件加载运行参数。"""
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def check_environment() -> int:
    """检查 Docker 服务是否可用，以及预构建的执行镜像是否存在。"""
    config = configuration()
    report = {"docker_service": False, "runner_image": False,
              "llm_api_key": bool(os.getenv("LLM_API_KEY")), "llm_model": os.getenv("LLM_MODEL")}
    try:
        import docker
        client = docker.from_env()
        client.ping()
        report["docker_service"] = True
        try:
            client.images.get(config["docker"]["image"])
            report["runner_image"] = True
        except docker.errors.ImageNotFound:
            pass
        client.close()
    except Exception as exc:
        report["docker_error"] = str(exc)
    print(json.dumps(report, indent=2))
    return 0 if report["docker_service"] and report["runner_image"] else 1


def generation_failure(output: Path, exc: Exception) -> None:
    """生成失败时也写出与执行任务一致的结果文件。"""
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").write_text(json.dumps({"status": "GENERATION_FAILED", "error": str(exc),
                                                     "duration_seconds": 0}, indent=2), encoding="utf-8")
    (output / "testcases.json").write_text('{"testcases": []}', encoding="utf-8")
    (output / "build.log").write_text("Generation failed; build was not attempted.\n", encoding="utf-8")
    (output / "execution.log").write_text(str(exc) + "\n", encoding="utf-8")
    suite = ET.Element("testsuite", name="generation", tests="0", failures="0", errors="1")
    case = ET.SubElement(suite, "testcase", name="generation")
    ET.SubElement(case, "error", message=str(exc))
    ET.ElementTree(suite).write(output / "test-results.xml", encoding="utf-8", xml_declaration=True)


def execute(project_dirs: list[Path], workers: int, mock_llm: bool) -> int:
    """生成测试、在 Docker 中执行，并为每个项目生成报告。"""
    config = configuration()
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = ROOT / "results" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    loader, generator = ProjectLoader(), TestCaseGenerator(ROOT / "prompts" / "testcase_generation.md",
                                                            config["generation"]["max_attempts"])
    builder = TaskBuilder(ROOT / "workspace")
    # 先完成生成再统一调度，使格式错误的 LLM 输出只影响当前项目，
    # 不会阻止其他有效项目进入 Docker 执行。
    projects, tasks, failures = {}, [], []
    multi = len(project_dirs) > 1
    for project_dir in project_dirs:
        project_id = project_dir.name
        output = run_dir / project_id if multi else run_dir
        output.mkdir(parents=True, exist_ok=True)
        try:
            project = loader.load(project_dir)
            if project.project_id in projects:
                raise ValueError(f"Duplicate project_id in this run: {project.project_id}")
            project_id, projects[project.project_id] = project.project_id, project
            generator.generate(project, output, mock=mock_llm)
            task = builder.build(project, output, output, run_id, config["test"]["process_timeout_seconds"])
            tasks.append(task)
        except Exception as exc:
            generation_failure(output, exc)
            failures.append((project_id, output))
    d = config["docker"]
    runner = DockerRunner(d["image"], d["memory"], d["nano_cpus"], d["container_timeout_seconds"],
                          d.get("pids_limit", 64))
    run_results = TaskScheduler(runner, workers).run(tasks) if tasks else []
    parser, reporter, summary = ResultParser(), ReportGenerator(), []
    for item in run_results:
        project, output = projects[item.task.project_id], item.task.output_dir
        result = parser.parse(output)
        reporter.project_report(project, result, output)
        relative_report = (output / "report.html").relative_to(run_dir).as_posix()
        summary.append({"project_id": project.project_id, "result": result,
                        "relative_report": relative_report})
    for project_id, output in failures:
        result = parser.parse(output)
        placeholder = type("ProjectInfo", (), {"project_id": project_id, "source_files": []})()
        reporter.project_report(placeholder, result, output)
        relative_report = (output / "report.html").relative_to(run_dir).as_posix()
        summary.append({"project_id": project_id, "result": result,
                        "relative_report": relative_report})
    if multi:
        reporter.summary_report(run_id, summary, run_dir)
    print(f"Run: {run_id}\nResults: {run_dir}")
    for item in sorted(summary, key=lambda x: x["project_id"]):
        print(f"  {item['project_id']}: {item['result']['status']}")
    return 0 if summary and all(x["result"]["status"] == "PASSED" for x in summary) else 1


def execute_generated(generation_run: Path, workers: int) -> int:
    """复用已有的 Codeflaws 生成批次执行测试，不再调用 LLM。"""
    generation_run = generation_run.resolve()
    summary_file = generation_run / "summary.json"
    if not summary_file.is_file():
        raise SystemExit(f"Generation summary does not exist: {summary_file}")
    records = json.loads(summary_file.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise SystemExit("Generation summary must contain a list")

    config = configuration()
    run_id = f"reuse-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = ROOT / "results" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    loader, builder = ProjectLoader(), TaskBuilder(ROOT / "workspace")
    projects, tasks, setup_failures = {}, [], []

    # 只有 GENERATED 记录可以执行；IMPORTED 和 GENERATION_FAILED 记录
    # 仍保留在原始生成摘要中，便于追踪批次处理情况。
    for record in records:
        if not isinstance(record, dict) or record.get("status") != "GENERATED":
            continue
        project_id = str(record.get("project_id", "")).strip()
        output = run_dir / project_id
        output.mkdir(parents=True, exist_ok=False)
        try:
            if not project_id or Path(project_id).name != project_id:
                raise ValueError(f"Invalid project_id: {project_id!r}")
            generated = generation_run / project_id
            for name in ("testcases.json", "test_generated.c"):
                source = generated / name
                if not source.is_file():
                    raise FileNotFoundError(f"Generated artifact does not exist: {source}")
                shutil.copy2(source, output / name)
            project_dir = ROOT / "inputs" / "codeflaws" / project_id
            project = loader.load(project_dir)
            if project.project_id != project_id:
                raise ValueError(f"Project ID mismatch: {project.project_id} != {project_id}")
            generation_metadata = json.loads((generated / "testcases.json").read_text(encoding="utf-8"))
            recorded_style = generation_metadata.get("test_style")
            if recorded_style is not None and recorded_style != project.test_style:
                raise ValueError(
                    f"Generated test style {recorded_style!r} does not match project style "
                    f"{project.test_style!r}; regenerate this batch")
            # 按当前项目模式重新校验已保存的 LLM 产物，防止旧的 fork 模式
            # 测试代码被误用于 direct_main 模式。
            validation_payload = {**generation_metadata,
                                  "test_code": (generated / "test_generated.c").read_text(encoding="utf-8")}
            generated_tests = GeneratedTests.model_validate(validation_payload)
            TestCaseGenerator._validate_for_project(generated_tests, project)
            projects[project_id] = project
            tasks.append(builder.build(project, generated, output, run_id,
                                       config["test"]["process_timeout_seconds"]))
        except Exception as exc:
            DockerRunner._infra_result(
                type("SetupTask", (), {"output_dir": output})(), "INFRA_ERROR", str(exc))
            setup_failures.append((project_id, output))

    if not tasks and not setup_failures:
        raise SystemExit("No GENERATED projects found in summary.json")
    d = config["docker"]
    runner = DockerRunner(d["image"], d["memory"], d["nano_cpus"], d["container_timeout_seconds"],
                          d.get("pids_limit", 64))
    run_results = TaskScheduler(runner, workers).run(tasks) if tasks else []
    parser, reporter, summary = ResultParser(), ReportGenerator(), []
    for item in run_results:
        project, output = projects[item.task.project_id], item.task.output_dir
        result = parser.parse(output)
        reporter.project_report(project, result, output)
        summary.append({"project_id": project.project_id, "result": result,
                        "relative_report": (output / "report.html").relative_to(run_dir).as_posix()})
    for project_id, output in setup_failures:
        result = parser.parse(output)
        placeholder = type("ProjectInfo", (), {"project_id": project_id, "source_files": []})()
        reporter.project_report(placeholder, result, output)
        summary.append({"project_id": project_id, "result": result,
                        "relative_report": (output / "report.html").relative_to(run_dir).as_posix()})
    reporter.summary_report(run_id, summary, run_dir)
    machine_summary = [{"project_id": item["project_id"], "status": item["result"]["status"],
                        "counts": item["result"]["counts"],
                        "relative_report": item["relative_report"]} for item in summary]
    (run_dir / "summary.json").write_text(
        json.dumps(machine_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Run: {run_id}\nResults: {run_dir}")
    for item in sorted(summary, key=lambda x: x["project_id"]):
        counts = item["result"]["counts"]
        print(f"  {item['project_id']}: {item['result']['status']} "
              f"(passed={counts['PASSED']}, failed={counts['FAILED']}, not_run={counts['NOT_RUN']})")
    return 0 if summary and all(x["result"]["status"] == "PASSED" for x in summary) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and execute isolated CMocka tests")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--project", type=Path)
    selection.add_argument("--all", action="store_true")
    selection.add_argument("--reuse-generated", type=Path,
                           help="Execute an existing Codeflaws generation batch without calling the LLM")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--mock-llm", action="store_true", help="Use labeled deterministic fixtures, not an LLM")
    parser.add_argument("--check-env", action="store_true")
    args = parser.parse_args()
    if not args.check_env and not (args.project or args.all or args.reuse_generated):
        parser.error("one of --project, --all, --reuse-generated, or --check-env is required")
    return args


def main() -> int:
    """命令行入口：先加载环境变量，再选择运行模式。"""
    load_dotenv(ROOT / ".env")
    args = parse_args()
    if args.check_env:
        return check_environment()
    if args.workers < 1:
        raise SystemExit("--workers must be at least 1")
    if args.reuse_generated:
        path = args.reuse_generated if args.reuse_generated.is_absolute() else Path.cwd() / args.reuse_generated
        return execute_generated(path, args.workers)
    dirs = sorted(p.parent for p in (ROOT / "inputs").glob("*/project.yaml")) if args.all else [args.project]
    if not dirs:
        raise SystemExit("No projects found")
    return execute([p if p.is_absolute() else (Path.cwd() / p) for p in dirs], args.workers, args.mock_llm)


if __name__ == "__main__":
    raise SystemExit(main())

