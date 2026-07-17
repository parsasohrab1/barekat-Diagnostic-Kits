"""انواع کیت تشخیصی."""

from barekat_diagnostics.kits.base import KitType, QCFlag, QCResult, QCSeverity
from barekat_diagnostics.kits.registry import get_kit_adapter

__all__ = ["KitType", "QCFlag", "QCResult", "QCSeverity", "get_kit_adapter"]
