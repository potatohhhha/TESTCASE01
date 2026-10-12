# LLM-AutoTest MVP

LLM-AutoTest turns a C project plus a requirements document into structured test cases and a complete CMocka test program, then compiles and runs it in an isolated Docker container. It supports a real OpenAI-compatible API and a clearly labeled deterministic `--mock-llm` fixture mode.

## Requirements

- Python 3.10+
- Docker Engine or Docker Desktop with Linux containers
- An OpenAI-compatible API key only for real LLM generation

## Install and build

```bash
cd LLM-AutoTest
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
docker build -t llm-autotest-runner:latest docker
python main.py --check-env
```

For real LLM use, copy `.env.example` to `.env` and set `LLM_API_KEY`, `LLM_MODEL`, and optionally `LLM_BASE_URL`. The API must implement OpenAI-compatible Chat Completions and JSON-object response format.

## Run

```bash
# One deterministic fixture; still performs real Docker compilation/execution
python main.py --project inputs/project_a --mock-llm

# Real LLM generation
python main.py --project inputs/project_a

# Four independent Docker tasks in parallel. This intentionally exits nonzero
# because project_fail and project_timeout are negative verification fixtures.
python main.py --all --workers 4 --mock-llm

# Automated tests; Docker integration runs only when daemon and image exist
python -m pytest -q
```

`project_a` and `project_pass2` pass. `project_fail` contains one deliberately incorrect assertion. `project_timeout` contains a deliberate infinite loop. These are fixed mock assets, not represented as LLM output.

## Inputs and outputs

Each `inputs/<name>/project.yaml` declares C sources, include directories, the requirement document, and compiler flags. Paths are resolved beneath that project directory; traversal outside it is rejected. TXT, Markdown, and DOCX requirement files are supported.

A single-project run writes the requested files directly to `results/<RUN_ID>/`. A multi-project run writes each project to `results/<RUN_ID>/<PROJECT_ID>/` and adds `results/<RUN_ID>/summary.html`. Every task has private input, output, and build directories. Inputs are mounted read-only in the container.

The runner disables networking and privilege escalation, drops all capabilities, uses a read-only root filesystem and non-root UID, limits memory/CPU, and never mounts the Docker socket. Test processes and containers have separate timeouts. Containers are removed after execution.

## Status meanings

- `PASSED`: build and all CMocka tests succeeded
- `FAILED`: CMocka reported a failed test
- `BUILD_FAILED`: GCC failed; the real diagnostics are in `build.log`
- `TIMEOUT`: test process or container exceeded its deadline
- `CRASHED`: the test executable terminated by a crash signal
- `GENERATION_FAILED`: project loading or LLM generation failed
- `INFRA_ERROR`: Docker or result infrastructure failed

The orchestration command returns zero only when every selected project is `PASSED`.
