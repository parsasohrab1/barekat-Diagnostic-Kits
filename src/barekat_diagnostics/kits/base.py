"""Abstraction layer for diagnostic kit types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class KitType(str, Enum):
  QPCR = "qpcr"
  ELISA = "elisa"
  SPECTROSCOPY = "spectroscopy"


class QCSeverity(str, Enum):
  INFO = "info"
  WARNING = "warning"
  CRITICAL = "critical"


@dataclass
class QCFlag:
  code: str
  message: str
  severity: QCSeverity = QCSeverity.WARNING


@dataclass
class QCResult:
  passed: bool
  flags: list[QCFlag] = field(default_factory=list)
  is_reliable: bool = True

  @property
  def warnings(self) -> list[str]:
    return [f.message for f in self.flags]


@dataclass
class ClinicalMetrics:
  primary_value: float | None
  cutoff: float | None
  confidence_interval: tuple[float, float] | None
  unit: str
  label: str


class KitAdapter(ABC):
  """Common interface for processing kit types."""

  kit_type: KitType
  default_cutoff: float

  @abstractmethod
  def extract_features(self, raw_data: dict[str, Any]) -> dict[str, float]:
    """Extract features from raw data."""

  @abstractmethod
  def run_qc(self, raw_data: dict[str, Any], features: dict[str, float]) -> QCResult:
    """Kit-type-specific quality control."""

  def get_cutoff(self, calibration: dict[str, Any] | None = None) -> float:
    if calibration and calibration.get("cutoff_value") is not None:
      return float(calibration["cutoff_value"])
    return self.default_cutoff

  @abstractmethod
  def build_clinical_metrics(
    self,
    features: dict[str, float],
    calibration: dict[str, Any] | None = None,
  ) -> ClinicalMetrics:
    """Build clinical metrics for the report."""

  def confidence_interval(self, value: float, confidence: float) -> tuple[float, float]:
    margin = (1.0 - confidence) * abs(value) * 0.1 + 0.5
    return (max(0.0, value - margin), value + margin)
