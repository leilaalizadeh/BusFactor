"""Shared test setup: uploaded documents go to a temporary folder, never into the repository."""
import pytest

from busfactor import orchestrator as orc


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path):
    previous = orc.UPLOADS
    orc.set_uploads_dir(tmp_path / "uploads")
    yield
    orc.set_uploads_dir(previous)
