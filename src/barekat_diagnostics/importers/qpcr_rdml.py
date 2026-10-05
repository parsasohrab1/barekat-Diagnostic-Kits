"""Importer for qPCR instrument RDML (XML) files."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from barekat_diagnostics.importers.qpcr_csv import _infer_role
from barekat_diagnostics.schemas import ImportedQpcrWell, SampleInput

# Common RDML namespaces
_NS_CANDIDATES = (
  "http://www.rdml.org",
  "http://www.rdml.org/version1",
  "",
)


def _local(tag: str) -> str:
  if "}" in tag:
    return tag.rsplit("}", 1)[-1]
  return tag


def _find_children(parent: ET.Element, name: str) -> list[ET.Element]:
  return [c for c in parent.iter() if _local(c.tag) == name and (c is parent or True)]


def _direct_children(parent: ET.Element, name: str) -> list[ET.Element]:
  return [c for c in list(parent) if _local(c.tag) == name]


def _attr(el: ET.Element, *names: str) -> str | None:
  for name in names:
    if name in el.attrib:
      return el.attrib[name]
    for key, val in el.attrib.items():
      if _local(key) == name:
        return val
  return None


def _text(el: ET.Element | None) -> str | None:
  if el is None or el.text is None:
    return None
  text = el.text.strip()
  return text or None


def _sample_map(root: ET.Element) -> dict[str, dict[str, str]]:
  samples: dict[str, dict[str, str]] = {}
  for el in root.iter():
    if _local(el.tag) != "sample":
      continue
    # A reference inside <react> usually has no children — do not rewrite the full definition
    children = list(el)
    if not children:
      continue
    sid = _attr(el, "id") or _text(next(iter(_direct_children(el, "id")), None))
    if not sid:
      continue
    stype = None
    description = None
    for child in children:
      local = _local(child.tag)
      if local in {"type", "sampleType"}:
        stype = _text(child) or _attr(child, "value")
      if local == "description":
        description = _text(child)
    samples[sid] = {"type": stype or "", "description": description or ""}
  return samples


def _extract_cq(react: ET.Element) -> float | None:
  for el in react.iter():
    local = _local(el.tag).lower()
    if local in {"cq", "ct", "cp"}:
      raw = _text(el) or _attr(el, "value")
      if raw:
        try:
          return float(raw.replace(",", "."))
        except ValueError:
          continue
  return None


def _extract_curve(react: ET.Element) -> list[float] | None:
  points: list[tuple[float, float]] = []
  for el in react.iter():
    if _local(el.tag) != "datapoint":
      continue
    cyc = None
    fluor = None
    for child in el:
      name = _local(child.tag).lower()
      if name in {"cyc", "cycle"}:
        try:
          cyc = float((_text(child) or "0").replace(",", "."))
        except ValueError:
          pass
      if name in {"fluor", "fluorescence", "tmp"}:
        try:
          fluor = float((_text(child) or "0").replace(",", "."))
        except ValueError:
          pass
    if cyc is not None and fluor is not None:
      points.append((cyc, fluor))
  if not points:
    return None
  points.sort(key=lambda p: p[0])
  return [p[1] for p in points]


def parse_qpcr_rdml(
  content: bytes | str,
  *,
  calibration_lot: str | None = None,
  default_kit_type: str = "qpcr",
) -> list[ImportedQpcrWell]:
  """Parse an RDML file into a list of wells."""
  text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
  try:
    root = ET.fromstring(text)
  except ET.ParseError as exc:
    raise ValueError(f"Invalid RDML file: {exc}") from exc

  sample_meta = _sample_map(root)
  wells: list[ImportedQpcrWell] = []
  index = 0

  for react in root.iter():
    if _local(react.tag) != "react":
      continue
    index += 1
    sample_id = None
    # sample id is often an attribute or under the sample sub-element
    for child in react:
      if _local(child.tag) == "sample":
        sample_id = _attr(child, "id") or _text(child)
        break
    if not sample_id:
      sample_id = _attr(react, "id") or f"RDML-{index}"

    well_pos = _attr(react, "id") or str(index)
    ct_value = _extract_cq(react)
    curve = _extract_curve(react)

    meta = sample_meta.get(sample_id, {})
    role = _infer_role(meta.get("type"), sample_id)

    target = None
    for child in react.iter():
      if _local(child.tag) == "target":
        target = _attr(child, "id") or _text(child)
        if target:
          break

    sample = SampleInput(
      sample_id=str(sample_id)[:32],
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
        well=str(well_pos),
        target=target,
        role=role,  # type: ignore[arg-type]
        source_format="rdml",
        raw_row={"sample_type": meta.get("type", ""), "description": meta.get("description", "")},
      )
    )

  if not wells:
    # fallback: if there is no react, build from the samples
    for sid, meta in sample_meta.items():
      role = _infer_role(meta.get("type"), sid)
      wells.append(
        ImportedQpcrWell(
          sample=SampleInput(
            sample_id=sid[:32],
            kit_type=default_kit_type,
            calibration_lot=calibration_lot,
            quality_score=0.5,
          ),
          role=role,  # type: ignore[arg-type]
          source_format="rdml",
          raw_row=meta,
        )
      )

  if not wells:
    raise ValueError("No reaction (react) or sample was found in the RDML")
  return wells


def rdml_info(content: bytes | str) -> dict[str, Any]:
  text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
  root = ET.fromstring(text)
  return {
    "root_tag": _local(root.tag),
    "version": _attr(root, "version") or root.attrib.get("version"),
    "namespaces": list(_NS_CANDIDATES),
  }
