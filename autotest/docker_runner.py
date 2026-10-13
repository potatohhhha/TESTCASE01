"""文件功能：在受限 Docker 沙箱中运行测试任务并处理基础设施异常。"""

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
        """在有资源限制的短生命周期 Docker 容器中运行一个任务。"""
        import docker
        client = docker.from_env()
        container = None
        try:
            # 生成的 C 代码不可信：关闭网络、移除 Linux capabilities、使用
            # 只读根文件系统，并且只挂载当前任务所需的目录。
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
            # 外层超时覆盖整个容器生命周期；容器内执行器还会对编译后的
            # 测试进程单独设置超时。
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
            # 正常运行结束后主动删除容器，不保留已停止的容器；报告和日志
            # 已通过可写输出挂载目录持久化到宿主机。
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
        """在 Linux 上沿用调用者的非 root UID，确保私有挂载目录可写。"""
        if hasattr(os, "getuid") and os.getuid() > 0:
            return f"{os.getuid()}:{os.getgid()}"
        return "10001:10001"

    @staticmethod
    def _infra_result(task: Task, status: str, message: str) -> None:
        """即使 Docker 无法运行任务，也生成完整的结果文件集合。"""
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

