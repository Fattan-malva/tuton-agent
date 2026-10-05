from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def scratch(tmp_path: Path) -> Path:
    """Temporary working directory for format/docx tests."""
    base = tmp_path / "scratch"
    base.mkdir(parents=True, exist_ok=True)
    return base
