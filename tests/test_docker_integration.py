import os
import subprocess
import sys
from pathlib import Path

import pytest

from autotest.docker_runner import DockerRunner
from autotest.project_loader import ProjectLoader
from autotest.task_builder import TaskBuilder

ROOT = Path(__file__).parents[1]


def docker_ready():
    try:
        import docker
        client = docker.from_env()
        client.ping()
        client.images.get("llm-autotest-runner:latest")
        client.close()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not docker_ready(), reason="Docker daemon or runner image unavailable")
def test_real_docker_pass_path():
    result = subprocess.run([sys.executable, "main.py", "--project", "inputs/project_a", "--mock-llm"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "project_a: PASSED" in result.stdout


@pytest.mark.skipif(not docker_ready(), reason="Docker daemon or runner image unavailable")
def test_direct_main_calls_renamed_main_in_process(workdir: Path):
    project_dir = workdir / "direct"
    project_dir.mkdir()
    (project_dir / "subject.c").write_text(
        "#include <stdio.h>\nint main(int argc, char **argv) { (void)argc; (void)argv; "
        "int x; if (scanf(\"%d\", &x) != 1) return 2; printf(\"%d\\n\", x * 2); return 0; }\n",
        encoding="utf-8")
    (project_dir / "requirements.md").write_text("Double one integer.\n", encoding="utf-8")
    (project_dir / "project.yaml").write_text(
        "project_id: direct\nsource_files: [subject.c]\ninclude_dirs: []\n"
        "requirements_file: requirements.md\ntest_style: direct_main\n"
        "compiler:\n  standard: gnu11\n  flags: [-Wall, -Wextra, -O0]\n  link_flags: []\n",
        encoding="utf-8")
    generated = workdir / "generated"
    generated.mkdir()
    (generated / "test_generated.c").write_text(r'''#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int codeflaws_main(int argc, char *argv[]);
static void test_TC001(void **state) {
    (void)state;
    char input[] = "21\n";
    char *captured = NULL;
    size_t captured_size = 0;
    FILE *input_stream = fmemopen(input, strlen(input), "r");
    FILE *output_stream = open_memstream(&captured, &captured_size);
    assert_non_null(input_stream);
    assert_non_null(output_stream);
    FILE *saved_stdin = stdin;
    FILE *saved_stdout = stdout;
    stdin = input_stream;
    stdout = output_stream;
    char *argv[] = {"program_under_test", NULL};
    int rc = codeflaws_main(1, argv);
    fflush(stdout);
    stdin = saved_stdin;
    stdout = saved_stdout;
    fclose(input_stream);
    fclose(output_stream);
    assert_int_equal(rc, 0);
    assert_string_equal(captured, "42\n");
    free(captured);
}
int main(void) {
    const struct CMUnitTest tests[] = {cmocka_unit_test(test_TC001)};
    return cmocka_run_group_tests(tests, NULL, NULL);
}
''', encoding="utf-8")
    project = ProjectLoader().load(project_dir)
    task = TaskBuilder(workdir / "workspace").build(
        project, generated, workdir / "output", "direct-run")
    result = DockerRunner(timeout_seconds=15, pids_limit=64).run(task)
    assert result.status == "PASSED", (task.output_dir / "build.log").read_text(encoding="utf-8")

