from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from .docker_runner import DockerRunner, RunnerResult
from .task_builder import Task


class TaskScheduler:
    def __init__(self, runner: DockerRunner, workers: int = 4):
        if workers < 1:
            raise ValueError("workers must be at least 1")
        self.runner, self.workers = runner, workers

    def run(self, tasks: list[Task]) -> list[RunnerResult]:
        results: list[RunnerResult] = []
        with ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="docker-task") as pool:
            futures = {pool.submit(self.runner.run, task): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    self.runner._infra_result(task, "INFRA_ERROR", str(exc))
                    results.append(RunnerResult(task, "INFRA_ERROR", str(exc)))
        return sorted(results, key=lambda item: item.task.project_id)

