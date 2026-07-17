"""SQLite local store for offline-first operation with resilient sync metadata."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from barekat_diagnostics.core.config import Settings, get_settings
from barekat_diagnostics.schemas import DiagnosisReport, SampleInput


class OfflineStore:
  """Local SQLite queue for samples and diagnoses without network."""

  def __init__(self, db_path: str | Path | None = None, settings: Settings | None = None):
    settings = settings or get_settings()
    self.settings = settings
    self.db_path = Path(db_path or settings.offline_sqlite_path)
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self._init_db()

  def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(str(self.db_path))
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with self._connect() as conn:
      conn.executescript("""
        CREATE TABLE IF NOT EXISTS pending_samples (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sample_id TEXT UNIQUE NOT NULL,
          sample_json TEXT NOT NULL,
          sync_status TEXT DEFAULT 'pending',
          created_at TEXT NOT NULL,
          synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS local_diagnoses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          sample_id TEXT NOT NULL,
          client_report_id TEXT UNIQUE,
          report_json TEXT NOT NULL,
          sync_status TEXT DEFAULT 'pending',
          sync_attempts INTEGER DEFAULT 0,
          last_error TEXT,
          device_id TEXT,
          center_id TEXT,
          tenant_id TEXT,
          conflict_resolution TEXT,
          created_at TEXT NOT NULL,
          synced_at TEXT
        );
        CREATE TABLE IF NOT EXISTS device_state (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pending_sync ON pending_samples(sync_status);
        CREATE INDEX IF NOT EXISTS idx_diagnosis_sync ON local_diagnoses(sync_status);
      """)
      # migrate older DBs missing columns
      cols = {r[1] for r in conn.execute("PRAGMA table_info(local_diagnoses)").fetchall()}
      migrations = {
        "client_report_id": "ALTER TABLE local_diagnoses ADD COLUMN client_report_id TEXT",
        "sync_attempts": "ALTER TABLE local_diagnoses ADD COLUMN sync_attempts INTEGER DEFAULT 0",
        "last_error": "ALTER TABLE local_diagnoses ADD COLUMN last_error TEXT",
        "device_id": "ALTER TABLE local_diagnoses ADD COLUMN device_id TEXT",
        "center_id": "ALTER TABLE local_diagnoses ADD COLUMN center_id TEXT",
        "tenant_id": "ALTER TABLE local_diagnoses ADD COLUMN tenant_id TEXT",
        "conflict_resolution": "ALTER TABLE local_diagnoses ADD COLUMN conflict_resolution TEXT",
      }
      for col, sql in migrations.items():
        if col not in cols:
          conn.execute(sql)

  def set_device_context(
    self,
    *,
    device_id: str | None = None,
    center_id: str | None = None,
    tenant_id: str | None = None,
  ) -> None:
    with self._connect() as conn:
      for key, val in {
        "device_id": device_id,
        "center_id": center_id,
        "tenant_id": tenant_id,
      }.items():
        if val is not None:
          conn.execute(
            "INSERT OR REPLACE INTO device_state (key, value) VALUES (?, ?)",
            (key, val),
          )

  def get_device_context(self) -> dict[str, str]:
    with self._connect() as conn:
      rows = conn.execute("SELECT key, value FROM device_state").fetchall()
    return {r["key"]: r["value"] for r in rows}

  def enqueue_sample(self, sample: SampleInput) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with self._connect() as conn:
      conn.execute(
        """INSERT OR REPLACE INTO pending_samples (sample_id, sample_json, sync_status, created_at)
           VALUES (?, ?, 'pending', ?)""",
        (sample.sample_id, json.dumps(sample.model_dump(), ensure_ascii=False), now),
      )

  def save_diagnosis(self, report: DiagnosisReport) -> str:
    now = datetime.now(timezone.utc).isoformat()
    ctx = self.get_device_context()
    client_report_id = f"CRPT-{uuid.uuid4().hex[:16].upper()}"
    payload = report.model_dump(mode="json")
    payload["client_report_id"] = client_report_id
    payload["device_id"] = ctx.get("device_id") or self.settings.edge_device_id
    payload["center_id"] = ctx.get("center_id") or self.settings.edge_center_id
    payload["tenant_id"] = ctx.get("tenant_id") or self.settings.edge_tenant_id

    with self._connect() as conn:
      conn.execute(
        """INSERT INTO local_diagnoses
           (sample_id, client_report_id, report_json, sync_status, sync_attempts,
            device_id, center_id, tenant_id, created_at)
           VALUES (?, ?, ?, 'pending', 0, ?, ?, ?, ?)""",
        (
          report.sample_id,
          client_report_id,
          json.dumps(payload, ensure_ascii=False),
          payload["device_id"],
          payload["center_id"],
          payload["tenant_id"],
          now,
        ),
      )
      conn.execute(
        "UPDATE pending_samples SET sync_status='completed' WHERE sample_id=?",
        (report.sample_id,),
      )
    return client_report_id

  def list_pending_sync(self, limit: int = 100) -> list[dict]:
    with self._connect() as conn:
      rows = conn.execute(
        """SELECT id, sample_id, client_report_id, report_json, sync_attempts
           FROM local_diagnoses
           WHERE sync_status IN ('pending', 'failed')
           ORDER BY id ASC LIMIT ?""",
        (limit,),
      ).fetchall()
    return [
      {
        "id": r["id"],
        "sample_id": r["sample_id"],
        "client_report_id": r["client_report_id"],
        "report": json.loads(r["report_json"]),
        "sync_attempts": r["sync_attempts"] or 0,
      }
      for r in rows
    ]

  def mark_synced(self, sample_id: str, client_report_id: str | None = None, resolution: str = "accepted") -> None:
    now = datetime.now(timezone.utc).isoformat()
    with self._connect() as conn:
      if client_report_id:
        conn.execute(
          """UPDATE local_diagnoses
             SET sync_status='synced', synced_at=?, conflict_resolution=?, last_error=NULL
             WHERE client_report_id=?""",
          (now, resolution, client_report_id),
        )
      else:
        conn.execute(
          """UPDATE local_diagnoses
             SET sync_status='synced', synced_at=?, conflict_resolution=?
             WHERE sample_id=? AND sync_status IN ('pending','failed')""",
          (now, resolution, sample_id),
        )

  def mark_failed(self, client_report_id: str, error: str) -> None:
    with self._connect() as conn:
      conn.execute(
        """UPDATE local_diagnoses
           SET sync_status='failed', sync_attempts=COALESCE(sync_attempts,0)+1, last_error=?
           WHERE client_report_id=?""",
        (error[:500], client_report_id),
      )

  def pending_count(self) -> int:
    with self._connect() as conn:
      row = conn.execute(
        "SELECT COUNT(*) as c FROM pending_samples WHERE sync_status='pending'"
      ).fetchone()
    return int(row["c"])

  def pending_sync_count(self) -> int:
    with self._connect() as conn:
      row = conn.execute(
        "SELECT COUNT(*) as c FROM local_diagnoses WHERE sync_status IN ('pending','failed')"
      ).fetchone()
    return int(row["c"])

  def get_sample(self, sample_id: str) -> SampleInput | None:
    with self._connect() as conn:
      row = conn.execute(
        "SELECT sample_json FROM pending_samples WHERE sample_id=?", (sample_id,)
      ).fetchone()
    if not row:
      return None
    return SampleInput.model_validate(json.loads(row["sample_json"]))
