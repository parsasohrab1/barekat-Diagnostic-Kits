"""Importer for qPCR instrument CSV output."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from barekat_diagnostics.schemas import ImportedQpcrWell, SampleInput

# Common column names in ABI / Bio-Rad / Roche / QuantStudio outputs
_SAMPLE_KEYS = ("sample", "sample_id", "sample id", "sample name", "samplename", "name")
_WELL_KEYS = ("well", "well_position", "position")
_CT_KEYS = ("ct", "cq", "cт", "ct mean", "cq mean", "threshold cycle")
_TARGET_KEYS = ("target", "gene", "assay", "detector", "target name")
_ROLE_KEYS = ("role", "sample type", "type", "control", "task")
_CURVE_KEYS = ("fluorescence", "curve", "raw fluorescence", "rn", "delta rn")


def _norm(header: str) -> str:
  return re.sub(r"\s+", " ", header.strip().lower().replace("_", " "))


def _find_col(headers: list[str], candidates: tuple[str, ...]) -> str | None:
  normalized = {_norm(h): h for h in headers}
  for cand in candidates:
    if cand in normalized:
      return normalized[cand]
  for key, original in normalized.items():
    for cand in candidates:
      if cand in key:
        return original
  return None


def _parse_ct(value: str | None) -> float | None:
  if value is None:
    return None
  text = value.strip()
  if not text or text.upper() in {"UND", "UNDETERMINED", "N/A", "NA", "-", "NULL"}:
    return None
  try:
    return float(text.replace(",", "."))
  except ValueError:
    return None


def _parse_curve(value: str | None) -> list[float] | None:
  if not value or not value.strip():
    return None
  parts = re.split(r"[;|\s]+", value.strip())
  points: list[float] = []
  for part in parts:
    if not part:
      continue
    try:
      points.append(float(part.replace(",", ".")))
    except ValueError:
      return None
  return points or None


def _infer_role(raw: str | None, sample_id: str) -> str:
  text = (raw or "").strip().lower()
  sid = sample_id.lower()
  if (
    text in {"positive", "pos", "pc", "positive control", "+", "posctrl"}
    or sid.startswith("pc")
    or "pos" in sid
  ):
    return "positive_control"
  if (
    text in {"negative", "neg", "nc", "ntc", "negative control", "-", "negctrl"}
    or sid.startswith("nc")
    or sid.startswith("ntc")
    or "neg" in sid
    or "ntc" in sid
  ):
    return "negative_control"
  return "patient"


def parse_qpcr_csv(
  content: bytes | str,
  *,
  calibration_lot: str | None = None,
  default_kit_type: str = "qpcr",
) -> list[ImportedQpcrWell]:
  """Parse a qPCR instrument CSV into a list of wells."""
  text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
  # Skip the metadata lines at the start of the file until reaching the header
  lines = text.splitlines()
  header_idx = 0
  for i, line in enumerate(lines[:40]):
    lower = line.lower()
    if "sample" in lower and ("ct" in lower or "cq" in lower or "well" in lower):
      header_idx = i
      break

  reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])))
  if not reader.fieldnames:
    raise ValueError("The CSV file has no valid header")

  headers = list(reader.fieldnames)
  sample_col = _find_col(headers, _SAMPLE_KEYS)
  well_col = _find_col(headers, _WELL_KEYS)
  ct_col = _find_col(headers, _CT_KEYS)
  target_col = _find_col(headers, _TARGET_KEYS)
  role_col = _find_col(headers, _ROLE_KEYS)
  curve_col = _find_col(headers, _CURVE_KEYS)

  if not sample_col and not well_col:
    raise ValueError("The Sample or Well column was not found in the CSV")
  if not ct_col:
    raise ValueError("The Ct/Cq column was not found in the CSV")

  wells: list[ImportedQpcrWell] = []
  seen: set[str] = set()

  for row_num, row in enumerate(reader, start=2):
    sample_raw = (row.get(sample_col) or "").strip() if sample_col else ""
    well_raw = (row.get(well_col) or "").strip() if well_col else ""
    if not sample_raw and not well_raw:
      continue

    sample_id = sample_raw or f"WELL-{well_raw}"
    # prevent duplicates within a file
    unique_key = f"{sample_id}|{well_raw}|{row.get(target_col) if target_col else ''}"
    if unique_key in seen:
      sample_id = f"{sample_id}-{row_num}"
    seen.add(unique_key)

    ct_value = _parse_ct(row.get(ct_col) if ct_col else None)
    role = _infer_role(row.get(role_col) if role_col else None, sample_id)
    curve = _parse_curve(row.get(curve_col) if curve_col else None)
    target = (row.get(target_col) or "").strip() if target_col else None

    sample = SampleInput(
      sample_id=sample_id[:32],
      kit_type=default_kit_type,
      calibration_lot=calibration_lot,
      ct_value=ct_value,
      curve_data=curve,
      quality_score=0.9 if ct_value is not None else 0.4,
      signal_to_noise=3.0 if ct_value is not None and ct_value < 40 else 1.0,
      amplification_efficiency=0.95 if ct_value is not None else 0.5,
    )

    wells.append(
      ImportedQpcrWell(
        sample=sample,
        well=well_raw or None,
        target=target,
        role=role,  # type: ignore[arg-type]
        source_format="csv",
        raw_row={k: (v or "") for k, v in row.items()},
      )
    )

  if not wells:
    raise ValueError("No valid sample was found in the CSV")
  return wells


def wells_summary(wells: list[ImportedQpcrWell]) -> dict[str, Any]:
  return {
    "total": len(wells),
    "patient": sum(1 for w in wells if w.role == "patient"),
    "positive_control": sum(1 for w in wells if w.role == "positive_control"),
    "negative_control": sum(1 for w in wells if w.role == "negative_control"),
    "with_ct": sum(1 for w in wells if w.sample.ct_value is not None),
  }
