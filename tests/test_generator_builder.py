"""文件功能：验证测试生成结果校验以及隔离任务目录的构建。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from autotest.project_loader import ProjectLoader
from autotest.task_builder import TaskBuilder
from autotest.testcase_generator import GeneratedTests, TestCaseGenerator as Generator, parse_json_object


ROOT = Path(__file__).parents[1]


def test_mock_generation_is_labeled_and_builds_isolated_task(workdir: Path):
    project = ProjectLoader().load(ROOT / "inputs" / "project_a")
    generated_dir = workdir / "generated"
    generated = Generator(ROOT / "prompts" / "testcase_generation.md").generate(
        project, generated_dir, mock=True)
    metadata = json.loads((generated_dir / "testcases.json").read_text(encoding="utf-8"))
    assert metadata["generation_mode"] == "mock_fixture"
    assert len(generated.testcases) == 5
    task = TaskBuilder(workdir / "workspace").build(project, generated_dir, workdir / "output", "run-1")
    assert (task.input_dir / "task.json").exists()
    assert task.input_dir != task.output_dir != task.build_dir
    assert "cmocka_run_group_tests" in (task.input_dir / "test_generated.c").read_text(encoding="utf-8")


def test_prompt_contains_every_required_input():
    project = ProjectLoader().load(ROOT / "inputs" / "project_a")
    prompt = Generator(ROOT / "prompts" / "testcase_generation.md")._prompt(project)
    assert "REQ001" in prompt
    assert "int limit_value" in prompt
    assert "#define LIMIT_H" in prompt
    assert '"standard": "c11"' in prompt
    assert "function name contains" in prompt


def test_validation_requires_testcase_id_in_resolved_function_name():
    payload = {
        "testcases": [{"testcase_id": "TC001", "requirement_id": "REQ001",
                       "description": "case", "inputs": {}, "expected": {"return_value": 1}}],
        "test_code": "int unrelated_test(void) { return 0; }",
    }
    with pytest.raises(ValidationError, match="no C test function containing its ID"):
        GeneratedTests.model_validate(payload)


def test_parse_json_object_accepts_fenced_object_and_rejects_array():
    assert parse_json_object('```json\n{"testcases": [], "test_code": "code"}\n```')["test_code"] == "code"
    with pytest.raises(ValueError, match="must be a JSON object"):
        parse_json_object("[0]")


def test_direct_main_validation_rejects_process_helpers():
    project = replace(ProjectLoader().load(ROOT / "inputs" / "project_a"), test_style="direct_main")
    generated = GeneratedTests.model_validate({
        "testcases": [{"testcase_id": "TC001", "requirement_id": "REQ001",
                       "description": "case", "inputs": {}, "expected": {}}],
        "test_code": """extern int codeflaws_main(int, char **);
static void test_TC001(void **state) { (void)state; fork(); }
void *a = fmemopen; void *b = open_memstream;
""",
    })
    with pytest.raises(ValueError, match="forbidden process helpers"):
        Generator._validate_for_project(generated, project)

