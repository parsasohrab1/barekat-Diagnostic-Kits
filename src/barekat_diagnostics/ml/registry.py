"""Strict model versioning, production lock, A/B and rollback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from barekat_diagnostics.core.config import Settings, get_settings


class RegistryError(Exception):
  def __init__(self, message: str) -> None:
    self.message = message
    super().__init__(message)


@dataclass
class ModelVersionInfo:
  version: str
  file: str
  algorithm: str
  features: list[str]
  metrics: dict
  dataset_hash: str
  created_at: str
  status: str = "staging"  # staging|validated|production|locked|rolled_back|retired
  file_checksum: str = ""
  locked: bool = False
  validation_protocol_id: str | None = None
  change_request_id: str | None = None


@dataclass
class ABTestConfig:
  enabled: bool = False
  challenger_version: str = ""
  traffic_pct: float = 0.1


@dataclass
class ModelRegistry:
  production_version: str = "v1"
  production_locked: bool = False
  versions: dict[str, ModelVersionInfo] = field(default_factory=dict)
  ab_test: ABTestConfig = field(default_factory=ABTestConfig)

  @classmethod
  def load(cls, path: Path | None = None) -> ModelRegistry:
    settings = get_settings()
    registry_path = path or (Path(settings.model_path) / "registry.json")
    if not registry_path.is_file():
      return cls()
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    versions: dict[str, ModelVersionInfo] = {}
    for k, v in data.get("versions", {}).items():
      known = {
        "version",
        "file",
        "algorithm",
        "features",
        "metrics",
        "dataset_hash",
        "created_at",
        "status",
        "file_checksum",
        "locked",
        "validation_protocol_id",
        "change_request_id",
      }
      payload = {key: v[key] for key in known if key in v}
      versions[k] = ModelVersionInfo(**payload)
    ab = data.get("ab_test", {})
    return cls(
      production_version=data.get("production_version", "v1"),
      production_locked=bool(data.get("production_locked", False)),
      versions=versions,
      ab_test=ABTestConfig(
        enabled=ab.get("enabled", False),
        challenger_version=ab.get("challenger_version", ""),
        traffic_pct=float(ab.get("traffic_pct", 0.1)),
      ),
    )

  def save(self, path: Path | None = None) -> None:
    settings = get_settings()
    registry_path = path or (Path(settings.model_path) / "registry.json")
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
      "production_version": self.production_version,
      "production_locked": self.production_locked,
      "versions": {k: v.__dict__ for k, v in self.versions.items()},
      "ab_test": self.ab_test.__dict__,
    }
    registry_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

  def route_version(self, routing_key: str | None) -> str:
    if not self.ab_test.enabled or not self.ab_test.challenger_version:
      return self.production_version
    if not routing_key:
      return self.production_version
    if self.production_locked and self.ab_test.enabled:
      # The production lock does not allow A/B unless the challenger is also validated
      challenger = self.versions.get(self.ab_test.challenger_version)
      if not challenger or challenger.status not in {"validated", "staging", "production"}:
        return self.production_version
    bucket = int(hashlib.md5(routing_key.encode()).hexdigest(), 16) % 100
    if bucket < int(self.ab_test.traffic_pct * 100):
      return self.ab_test.challenger_version
    return self.production_version

  def model_file(self, version: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if version in self.versions:
      return self.versions[version].file
    return settings.classifier_model

  def register_version(
    self,
    version: str,
    file: str,
    algorithm: str,
    features: list[str],
    metrics: dict,
    dataset_hash: str,
    *,
    promote: bool = False,
    file_checksum: str = "",
    allow_overwrite: bool = False,
    settings: Settings | None = None,
  ) -> tuple[bool, str]:
    """Register a new version — overwriting an existing version is forbidden unless allow_overwrite."""
    settings = settings or get_settings()

    if version in self.versions and not allow_overwrite:
      existing = self.versions[version]
      if existing.status in {"production", "locked"} or existing.locked:
        raise RegistryError(
          f"Version {version} is locked/production and cannot be overwritten — use a new version identifier"
        )
      raise RegistryError(
        f"Version {version} is already registered — strict versioning does not allow overwrite"
      )

    if not file_checksum and file:
      file_checksum = file_sha256(Path(settings.model_path) / file)

    self.versions[version] = ModelVersionInfo(
      version=version,
      file=file,
      algorithm=algorithm,
      features=features,
      metrics=metrics,
      dataset_hash=dataset_hash,
      created_at=datetime.now(timezone.utc).isoformat(),
      status="staging",
      file_checksum=file_checksum,
      locked=False,
    )

    message = "registered as staging"
    should_promote = promote

    if promote:
      if self.production_locked:
        should_promote = False
        message = "promotion blocked — production is locked; use change control + unlock"
      elif self.production_version in self.versions:
        prod_metrics = self.versions[self.production_version].metrics
        if not _passes_quality_gate(metrics, prod_metrics, settings):
          should_promote = False
          message = "promotion blocked — performance below production threshold"

    if should_promote:
      self._set_production(version)
      message = "promoted to production"

    self.save()
    return should_promote, message

  def promote(
    self,
    version: str,
    *,
    change_request_id: str | None = None,
    validation_protocol_id: str | None = None,
    force: bool = False,
    settings: Settings | None = None,
  ) -> str:
    """Explicit promotion to production — requires being unlocked or force from change control."""
    settings = settings or get_settings()
    if version not in self.versions:
      raise RegistryError(f"Version {version} not found")
    if self.production_locked and not force:
      raise RegistryError("Production is locked — unlock first or an approved change request is required")

    info = self.versions[version]
    if self.production_version in self.versions and not force:
      if not _passes_quality_gate(info.metrics, self.versions[self.production_version].metrics, settings):
        raise RegistryError("Promotion rejected — quality criteria below the production threshold")

    if validation_protocol_id:
      info.validation_protocol_id = validation_protocol_id
    if change_request_id:
      info.change_request_id = change_request_id

    self._set_production(version)
    self.save()
    return f"promoted {version} to production"

  def lock_production(self) -> None:
    if self.production_version not in self.versions:
      raise RegistryError("There is no production version to lock")
    self.production_locked = True
    prod = self.versions[self.production_version]
    prod.locked = True
    prod.status = "locked"
    self.save()

  def unlock_production(self, *, change_request_id: str | None = None) -> None:
    self.production_locked = False
    if self.production_version in self.versions:
      prod = self.versions[self.production_version]
      prod.locked = False
      prod.status = "production"
      if change_request_id:
        prod.change_request_id = change_request_id
    self.save()

  def mark_validated(self, version: str, protocol_id: str) -> None:
    if version not in self.versions:
      raise RegistryError(f"Version {version} not found")
    info = self.versions[version]
    if info.status == "production" and info.locked:
      raise RegistryError("A locked version cannot have its status changed")
    info.status = "validated" if info.status != "production" else info.status
    info.validation_protocol_id = protocol_id
    self.save()

  def force_rollback(self, to_version: str) -> str:
    """Manual rollback to a specific version (admin/change control)."""
    if to_version not in self.versions:
      raise RegistryError(f"Target version {to_version} not found")
    prev = self.production_version
    if prev in self.versions:
      self.versions[prev].status = "rolled_back"
      self.versions[prev].locked = False
    self.production_locked = False
    self._set_production(to_version)
    self.save()
    return f"rolled back from {prev} to {to_version}"

  def rollback_if_degraded(self, version: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if version not in self.versions or self.production_version != version:
      return False
    if self.production_locked:
      return False

    candidates = sorted(self.versions.values(), key=lambda v: v.created_at, reverse=True)
    for candidate in candidates:
      if candidate.version == version:
        continue
      if candidate.status in ("production", "staging", "validated", "locked"):
        if _passes_quality_gate(candidate.metrics, self.versions[version].metrics, settings):
          self._set_production(candidate.version)
          self.versions[version].status = "rolled_back"
          self.save()
          return True
    return False

  def _set_production(self, version: str) -> None:
    for v in self.versions.values():
      if v.status in {"production", "locked"}:
        v.status = "staging"
        v.locked = False
    self.versions[version].status = "production"
    self.versions[version].locked = False
    self.production_version = version
    self.production_locked = False

  def get_production_metrics(self) -> dict | None:
    if self.production_version in self.versions:
      return self.versions[self.production_version].metrics
    return None


def _passes_quality_gate(new_metrics: dict, baseline_metrics: dict, settings: Settings) -> bool:
  threshold = settings.ml_rollback_threshold
  for key in ("sensitivity", "specificity", "roc_auc"):
    new_val = _metric_value(new_metrics, key)
    base_val = _metric_value(baseline_metrics, key)
    if base_val > 0 and new_val < base_val - threshold:
      return False
  return True


def _metric_value(metrics: dict, key: str) -> float:
  raw = metrics.get(key)
  if isinstance(raw, dict):
    return float(raw.get("value", 0))
  if raw is None:
    return 0.0
  return float(raw)


def dataset_hash(df) -> str:
  import pandas as pd

  if not isinstance(df, pd.DataFrame):
    return ""
  # content hash: row count + positives alone would collide for distinct datasets
  cols = sorted(c for c in df.columns if df[c].map(lambda v: isinstance(v, (list, dict))).sum() == 0)
  row_hashes = pd.util.hash_pandas_object(df[cols], index=False).values
  h = hashlib.sha256(",".join(cols).encode())
  h.update(row_hashes.tobytes())
  return h.hexdigest()[:16]


def file_sha256(path: Path) -> str:
  if not path.is_file():
    return ""
  h = hashlib.sha256()
  with path.open("rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
      h.update(chunk)
  return h.hexdigest()[:32]
