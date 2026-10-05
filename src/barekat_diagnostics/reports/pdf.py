"""Generate the diagnosis report PDF."""

from io import BytesIO

from fpdf import FPDF

from barekat_diagnostics.schemas import DiagnosisReport

_RECOMMENDATION_EN = {
  "report": "Report",
  "retest": "Retest Required",
  "invalid": "Invalid - Do Not Report",
  "reassess": "Reassessment Suggested",
}

_RESULT_EN = {
  "positive": "Positive",
  "negative": "Negative",
  "inconclusive": "Inconclusive",
}

_SEVERITY_EN = {
  "info": "INFO",
  "warning": "WARNING",
  "critical": "CRITICAL",
}


def generate_report_pdf(report: DiagnosisReport) -> bytes:
  pdf = FPDF()
  pdf.set_auto_page_break(auto=True, margin=15)
  pdf.add_page()
  pdf.set_font("Helvetica", size=11)

  def writeln(text: str, h: float = 7) -> None:
    pdf.cell(0, h, text, new_x="LMARGIN", new_y="NEXT")

  writeln("barekat Diagnostic Report", h=10)
  pdf.ln(4)
  writeln(f"Sample ID: {report.sample_id}")
  writeln(f"Kit Type: {report.kit_type.upper()}")
  writeln(f"Result: {_RESULT_EN.get(report.result, report.result)}")
  writeln(f"Confidence: {report.confidence * 100:.1f} percent")
  writeln(f"Recommendation: {_RECOMMENDATION_EN.get(report.recommendation, report.recommendation)}")
  writeln(f"QC Passed: {'Yes' if report.qc_passed else 'No'}")
  pdf.ln(2)

  metrics = report.clinical_metrics
  primary = metrics.primary_value if metrics.primary_value is not None else "N/A"
  cutoff = metrics.cutoff if metrics.cutoff is not None else "N/A"
  writeln(f"{metrics.label}: {primary} {metrics.unit}")
  writeln(f"Cutoff: {cutoff}")

  if metrics.confidence_interval:
    lo, hi = metrics.confidence_interval
    writeln(f"95 pct CI: [{lo:.2f}, {hi:.2f}]")

  pdf.ln(2)
  writeln("QC Flags:")
  if report.qc_flags:
    for flag in report.qc_flags:
      sev = _SEVERITY_EN.get(flag.severity, flag.severity)
      writeln(f"  [{sev}] {flag.code}")
  else:
    writeln("  None")

  pdf.ln(2)
  writeln(f"Model Version: {report.model_version}")

  if report.clinical_explanation:
    pdf.ln(2)
    writeln("Clinical interpretation:")
    writeln(f"  {report.clinical_explanation.summary}")
    if report.clinical_explanation.confidence_note:
      writeln(f"  Note: {report.clinical_explanation.confidence_note}")
    for insight in report.clinical_explanation.insights[:6]:
      writeln(f"  - [{insight.category}] {insight.title}: {insight.detail[:120]}")

  if report.reassessment_suggested:
    pdf.ln(2)
    writeln(f"Reassessment suggested: {report.reassessment_id or 'yes'}")

  buffer = BytesIO()
  pdf.output(buffer)
  return buffer.getvalue()
