"""ثبت و بازیابی آداپتور کیت."""

from barekat_diagnostics.kits.base import KitAdapter, KitType
from barekat_diagnostics.kits.elisa import ElisaKitAdapter
from barekat_diagnostics.kits.qpcr import QpcrKitAdapter
from barekat_diagnostics.kits.spectroscopy import SpectroscopyKitAdapter

_ADAPTERS: dict[KitType, KitAdapter] = {
  KitType.QPCR: QpcrKitAdapter(),
  KitType.ELISA: ElisaKitAdapter(),
  KitType.SPECTROSCOPY: SpectroscopyKitAdapter(),
}


def get_kit_adapter(kit_type: str | KitType) -> KitAdapter:
  if isinstance(kit_type, str):
    try:
      kit_type = KitType(kit_type.lower())
    except ValueError as exc:
      raise ValueError(f"نوع کیت نامعتبر: {kit_type}") from exc
  if kit_type not in _ADAPTERS:
    raise ValueError(f"آداپتور برای {kit_type} پیاده‌سازی نشده")
  return _ADAPTERS[kit_type]
