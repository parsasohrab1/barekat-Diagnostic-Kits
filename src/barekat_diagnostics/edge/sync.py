"""Sync مقاوم در برابر قطعی شبکه با retry/backoff و حل تعارض."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.edge.offline_store import OfflineStore
from barekat_diagnostics.schemas import DiagnosisReport


class OfflineSyncService:
  """Push pending local diagnoses to server when network is available."""

  def __init__(self, settings: Settings | None = None):
    self.settings = settings or get_settings()
    self.store = OfflineStore(settings=self.settings)

  def sync_all(self, api_base: str | None = None) -> dict:
    base = (api_base or self.settings.offline_sync_api_url).rstrip("/")
    pending = self.store.list_pending_sync(limit=self.settings.edge_sync_batch_size)
    synced = 0
    failed = 0
    conflicts = 0
    errors: list[str] = []
    max_attempts = self.settings.edge_sync_max_retries

    for item in pending:
      sample_id = item["sample_id"]
      client_report_id = item.get("client_report_id")
      attempts = int(item.get("sync_attempts") or 0)
      if attempts >= max_attempts:
        failed += 1
        errors.append(f"{sample_id}: max retries exceeded")
        continue

      report = DiagnosisReport.model_validate(item["report"])
      payload = {
        "report": report.model_dump(mode="json"),
        "client_report_id": client_report_id,
        "device_id": item["report"].get("device_id") or self.settings.edge_device_id,
        "center_id": item["report"].get("center_id") or self.settings.edge_center_id,
        "tenant_id": item["report"].get("tenant_id") or self.settings.edge_tenant_id,
        "conflict_policy": self.settings.edge_conflict_policy,
      }
      ok, status, detail = self._post_with_retry(f"{base}/diagnosis/sync", payload)
      if ok:
        resolution = detail.get("resolution", "accepted") if isinstance(detail, dict) else "accepted"
        if resolution in {"rejected_duplicate", "server_wins"}:
          conflicts += 1
        self.store.mark_synced(sample_id, client_report_id, resolution=resolution)
        synced += 1
      else:
        failed += 1
        err = f"{sample_id}: {status} {detail}"
        errors.append(err)
        if client_report_id:
          self.store.mark_failed(client_report_id, err)

    return {
      "synced": synced,
      "failed": failed,
      "pending": self.store.pending_sync_count(),
      "conflicts": conflicts,
      "errors": errors,
    }

  def _post_with_retry(self, url: str, payload: dict) -> tuple[bool, str, dict | str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = self.settings.edge_sync_token
    if token:
      headers["Authorization"] = f"Bearer {token}"
    device_id = self.settings.edge_device_id
    if device_id:
      headers["X-Edge-Device-Id"] = device_id

    retries = self.settings.edge_sync_max_retries
    backoff = self.settings.edge_sync_backoff_seconds
    last_err: str = "unknown"

    for attempt in range(retries):
      req = urllib.request.Request(url, data=body, headers=headers, method="POST")
      try:
        with urllib.request.urlopen(req, timeout=self.settings.edge_sync_timeout_seconds) as resp:
          raw = resp.read().decode("utf-8")
          detail: dict | str
          try:
            detail = json.loads(raw) if raw else {}
          except json.JSONDecodeError:
            detail = raw
          if resp.status in (200, 201, 409):
            # 409 = conflict resolved on server (still mark synced per policy)
            return True, str(resp.status), detail if isinstance(detail, dict) else {"raw": detail}
          last_err = f"HTTP {resp.status}"
      except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
          detail = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
          detail = raw
        if exc.code == 409:
          return True, "409", detail if isinstance(detail, dict) else {"resolution": "rejected_duplicate"}
        last_err = f"HTTP {exc.code}: {detail}"
        # 4xx non-conflict: don't retry endlessly
        if 400 <= exc.code < 500 and exc.code != 429:
          return False, str(exc.code), detail if isinstance(detail, dict) else last_err
      except urllib.error.URLError as exc:
        last_err = str(exc.reason)
      except TimeoutError:
        last_err = "timeout"

      if attempt < retries - 1:
        time.sleep(backoff * (2**attempt))

    return False, "failed", last_err

  def export_pending_json(self) -> str:
    return json.dumps(self.store.list_pending_sync(), ensure_ascii=False, indent=2)
