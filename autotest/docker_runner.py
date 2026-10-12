from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .task_builder import Task


@dataclass(frozen=True)
class RunnerResult:
    task: Task
    status: str
    error: str | None = None


class DockerRunner:
    def __init__(self, image: str = "llm-autotest-runner:latest", memory: str = "512m",
                 nano_cpus: int = 1_000_000_000, timeout_seconds: float = 30,
                 pids_limit: int = 64):
        self.image, self.memory, self.nano_cpus = image, memory, nano_cpus
        self.timeout_seconds = timeout_seconds
        self.pids_limit = pids_limit

    def run(self, task: Task) -> RunnerResult:
        import docker
        client = docker.from_env()
        container = None
        try:
            container = client.containers.run(
                self.image, detach=True, network_disabled=True, privileged=False,
                user=self._container_user(), mem_limit=self.memory, nano_cpus=self.nano_cpus,
                pids_limit=self.pids_limit,
                cap_drop=["ALL"], security_opt=["no-new-privileges:true"], read_only=True,
                tmpfs={"/tmp": "rw,noexec,nosuid,size=16m"},
                volumes={
                    str(task.input_dir): {"bind": "/task/input", "mode": "ro"},
                    str(task.output_dir): {"bind": "/task/output", "mode": "rw"},
                    str(task.build_dir): {"bind": "/task/build", "mode": "rw"},
                }, labels={"llm-autotest.run_id": task.run_id, "llm-autotest.task_id": task.task_id})
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                container.reload()
                if container.status in ("exited", "dead"):
                    break
                time.sleep(0.2)
            else:
                container.kill()
                self._infra_result(task, "TIMEOUT", f"Container exceeded {self.timeout_seconds}s")
                return RunnerResult(task, "TIMEOUT", "container timeout")
            result_file = task.output_dir / "result.json"
            if not result_file.exists():
                logs = container.logs(stdout=True, stderr=True).decode(errors="replace")
                self._infra_result(task, "INFRA_ERROR", f"Container produced no result.json\n{logs}")
            status = json.loads(result_file.read_text(encoding="utf-8"))["status"]
            return RunnerResult(task, status)
        except Exception as exc:
            self._infra_result(task, "INFRA_ERROR", str(exc))
            return RunnerResult(task, "INFRA_ERROR", str(exc))
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            try:
                client.close()
            except Exception:
                pass

    @staticmethod
    def _container_user() -> str:
        """Use the invoking non-root UID on Linux so private bind mounts stay writable."""
        if hasattr(os, "getuid") and os.getuid() > 0:
            return f"{os.getuid()}:{os.getgid()}"
        return "10001:10001"

    @staticmethod
    def _infra_result(task: Task, status: str, message: str) -> None:
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "result.json").write_text(
            json.dumps({"status": status, "error": message, "duration_seconds": 0}, indent=2), encoding="utf-8")
        for name in ("build.log", "execution.log"):
            path = task.output_dir / name
            if not path.exists():
                path.write_text(message + "\n", encoding="utf-8")
        xml_path = task.output_dir / "test-results.xml"
        if not xml_path.exists():
            suite = ET.Element("testsuite", name="infrastructure", tests="0", failures="0", errors="1")
            case = ET.SubElement(suite, "testcase", name="infrastructure")
            ET.SubElement(case, "error", message=message)
            ET.ElementTree(suite).write(xml_path, encoding="utf-8", xml_declaration=True)

