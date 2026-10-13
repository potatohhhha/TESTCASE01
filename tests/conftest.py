"""文件功能：为自动化测试提供独立的临时工作目录夹具。"""

import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workdir() -> Path:
    """A sandbox-friendly alternative to pytest's chmod-based tmp_path on Windows."""
    path = Path(__file__).parents[1] / "workspace" / "test-artifacts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path

