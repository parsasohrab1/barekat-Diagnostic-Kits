"""Quality control — wrapper compatible with kit adapters."""

from barekat_diagnostics.kits.registry import get_kit_adapter
from barekat_diagnostics.pipeline.report import sample_to_raw_data
from barekat_diagnostics.schemas import SampleInput

# Re-export for backward compatibility
from barekat_diagnostics.kits.base import QCResult  # noqa: F401


def run_qc(sample: SampleInput, settings=None) -> QCResult:
  """Run QC through the kit adapter."""
  adapter = get_kit_adapter(sample.kit_type)
  raw_data = sample_to_raw_data(sample)
  features = adapter.extract_features(raw_data)
  return adapter.run_qc(raw_data, features)
