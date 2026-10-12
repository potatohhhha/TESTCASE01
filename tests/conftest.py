import uuid
from pathlib import Path

import pytest


@pytest.fixture
def workdir() -> Path:
    """A sandbox-friendly alternative to pytest's chmod-based tmp_path on Windows."""
    path = Path(__file__).parents[1] / "workspace" / "test-artifacts" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path

