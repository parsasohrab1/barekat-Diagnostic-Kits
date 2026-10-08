"""Keep tests from writing into the repository's tracked data/models registry."""

import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolated_model_dir():
  from barekat_diagnostics.core import config

  with tempfile.TemporaryDirectory(prefix="barekat-models-") as tmp:
    mp = pytest.MonkeyPatch()
    mp.setenv("MODEL_PATH", tmp)
    config.get_settings.cache_clear()
    yield tmp
    mp.undo()
    config.get_settings.cache_clear()
