from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from jinja2 import Template
from pydantic import BaseModel, Field, model_validator

from .project_loader import Project


class TestCase(BaseModel):
    testcase_id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    requirement_id: str
    description: str
    inputs: dict[str, Any]
    expected: dict[str, Any]
    unresolved: bool = False


class GeneratedTests(BaseModel):
    testcases: list[TestCase] = Field(min_length=1)
    test_code: str = Field(min_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [case.testcase_id for case in self.testcases]
        if len(ids) != len(set(ids)):
            raise ValueError("testcase_id values must be unique")
        for case in self.testcases:
            if case.unresolved:
                continue
            function_names = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", self.test_code)
            if not any(case.testcase_id in name for name in function_names):
                raise ValueError(
                    f"Resolved testcase {case.testcase_id} has no C test function containing its ID"
                )
        return self


PASS_CASES = [
    ("TC001", "REQ001", "below lower bound", {"x": -1, "min": 0, "max": 10}, 0),
    ("TC002", "REQ002", "above upper bound", {"x": 11, "min": 0, "max": 10}, 10),
    ("TC003", "REQ003", "inside range", {"x": 5, "min": 0, "max": 10}, 5),
    ("TC004", "REQ004", "equal lower bound", {"x": 0, "min": 0, "max": 10}, 0),
    ("TC005", "REQ004", "equal upper bound", {"x": 10, "min": 0, "max": 10}, 10),
]


def mock_payload(profile: str) -> dict[str, Any]:
    cases = [{"testcase_id": i, "requirement_id": r, "description": d, "inputs": x,
              "expected": {"return_value": expected}, "unresolved": False}
             for i, r, d, x, expected in PASS_CASES]
    test_functions = []
    registrations = []
    for index, (case_id, _, _, inputs, expected) in enumerate(PASS_CASES):
        actual_expected = expected + 1 if profile == "fail" and index == 0 else expected
        body = ("    for (;;) {}" if profile == "timeout" and index == 0 else
                f"    assert_int_equal(limit_value({inputs['x']}, {inputs['min']}, {inputs['max']}), {actual_expected});")
        test_functions.append(f"static void {case_id}(void **state) {{\n    (void)state;\n{body}\n}}")
        registrations.append(f"cmocka_unit_test({case_id})")
    code = """#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include "limit.h"

%s

int main(void) {
    const struct CMUnitTest tests[] = {%s};
    return cmocka_run_group_tests(tests, NULL, NULL);
}
""" % ("\n\n".join(test_functions), ", ".join(registrations))
    return {"testcases": cases, "test_code": code}


class TestCaseGenerator:
    def __init__(self, prompt_path: str | Path, max_attempts: int = 3):
        self.prompt_path = Path(prompt_path)
        self.max_attempts = max_attempts

    def _prompt(self, project: Project) -> str:
        template = Template(self.prompt_path.read_text(encoding="utf-8"))
        sources = "\n\n".join(f"--- {p.name} ---\n{p.read_text(encoding='utf-8')}" for p in project.source_files)
        headers = "\n\n".join(f"--- {p.name} ---\n{p.read_text(encoding='utf-8')}" for p in project.header_files)
        return template.render(requirements=project.requirements.text, sources=sources,
                               headers=headers, compiler=json.dumps(project.compiler),
                               test_style=project.test_style)

    @staticmethod
    def _validate_for_project(generated: GeneratedTests, project: Project) -> None:
        if project.test_style == "function":
            return
        code = generated.test_code
        if project.test_style == "console":
            if re.search(r"\b(?:system|popen)\s*\(", code):
                raise ValueError("Console tests must not invoke a shell via system() or popen()")
            required = ("fork", "pipe", "dup2", "waitpid")
            missing = [name for name in required if not re.search(rf"\b{name}\s*\(", code)]
            if "PROGRAM_UNDER_TEST" not in code:
                missing.append("PROGRAM_UNDER_TEST")
            if missing:
                raise ValueError(f"Console test code is missing safe process helper elements: {missing}")
        elif project.test_style == "direct_main":
            forbidden = ("fork", "pipe", "dup2", "execl", "execv", "waitpid", "system", "popen")
            used = [name for name in forbidden if re.search(rf"\b{name}\s*\(", code)]
            if "PROGRAM_UNDER_TEST" in code:
                used.append("PROGRAM_UNDER_TEST")
            if used:
                raise ValueError(f"direct_main tests contain forbidden process helpers: {used}")
            required = ("codeflaws_main", "fmemopen", "open_memstream")
            missing = [name for name in required if not re.search(rf"\b{name}\b", code)]
            if missing:
                raise ValueError(f"direct_main test code is missing direct-call elements: {missing}")
        for source in project.source_files:
            if f'#include "{source.name}"' in code:
                raise ValueError(f"{project.test_style} tests must not include the production source")

    def generate(self, project: Project, output_dir: str | Path, mock: bool = False) -> GeneratedTests:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        if mock:
            raw = mock_payload(project.mock_profile)
        else:
            api_key = os.getenv("LLM_API_KEY")
            if not api_key:
                raise RuntimeError("LLM_API_KEY is required unless --mock-llm is used")
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=os.getenv("LLM_BASE_URL") or None)
            last_error: Exception | None = None
            for _ in range(self.max_attempts):
                try:
                    response = client.chat.completions.create(
                        model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                        messages=[{"role": "user", "content": self._prompt(project)}],
                        response_format={"type": "json_object"}, temperature=0)
                    raw = json.loads(response.choices[0].message.content or "")
                    candidate = GeneratedTests.model_validate(raw)
                    self._validate_for_project(candidate, project)
                    break
                except Exception as exc:
                    last_error = exc
            else:
                raise RuntimeError(f"LLM did not return valid test JSON after {self.max_attempts} attempts: {last_error}")
        generated = GeneratedTests.model_validate(raw)
        self._validate_for_project(generated, project)
        metadata = generated.model_dump(exclude={"test_code"})
        metadata["generation_mode"] = "mock_fixture" if mock else "llm"
        metadata["test_style"] = project.test_style
        (output / "testcases.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        (output / "test_generated.c").write_text(generated.test_code, encoding="utf-8")
        return generated
