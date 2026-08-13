"""Downloadable Markdown summary of a completed analysis, for a user who
wants to forward what the tool found -- to a contractor, a client, or
their own inbox.

Same rule as every other module under app/: it composes no analysis. Every
line is a fact already on the PermitAnalysisResult, rendered as text
instead of as widgets. It deliberately reuses formatting.py's label maps
rather than writing its own wording, so the export and the screen never
drift into describing the same finding differently.

Two things about an exported file that do not apply to the page it came
from, and that shape what is here:

1. It travels. A download gets forwarded and read by people who never saw
   this app, so the disclaimer is embedded in the file itself rather than
   left behind on screen. Agent 3's own disclaimer string is used, not a
   paraphrase. It is placed at the top, where a forwarded document is
   actually read, and repeated at the end.

2. It is a snapshot, not a feed. The permit keeps moving after the file is
   written, so the header states when it was generated and that it will
   not update -- otherwise a month-old attachment reads as current status.

build_report() is a pure function of the result so it can be tested
without Streamlit; render() is the thin widget half.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from formatting import (
    CATEGORY_LABELS,
    DATA_QUALITY_FLAG_LABELS,
    MATCH_STATUS_LABELS,
    SEVERITY_LABELS,
    outcome_headline,
)
from i18n import t
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult

_SOURCES_NOTE = (
    "Built from two City of Los Angeles open datasets: Building and Safety "
    "permits (gwh9-jnip) and Building and Safety inspections (9w5z-rg2h)."
)


def _fmt(value: object) -> str:
    """Dates as ISO, None as an em dash. Nothing else is reformatted --
    numbers and source strings are carried through exactly as the pipeline
    produced them."""
    if value is None or value == "":
        return "—"
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def build_report(result: PermitAnalysisResult, *, generated_at: datetime | None = None) -> str:
    """The report as Markdown. Pure -- no Streamlit, no clock unless one is
    injected, so a test can assert the whole document byte for byte."""
    now = generated_at or datetime.now(timezone.utc)
    snapshot = result.journey.latest_snapshot
    lines: list[str] = []

    lines.append(f"# Permit {result.permit_number}")
    lines.append("")
    # Disclaimer first: this file will be read by people who never saw the
    # app, and a caveat at the bottom of a forwarded document is a caveat
    # nobody reads.
    lines.append(f"> **{result.developer_explanations.disclaimer}**")
    lines.append(">")
    lines.append(
        f"> Generated {now.strftime('%Y-%m-%d %H:%M UTC')}. This is a snapshot and does "
        "not update -- re-run the tool for current status."
    )
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Result:** {outcome_headline(result)}")
    lines.append(
        f"- **Status:** {_fmt(snapshot.status_desc if snapshot else None)}"
    )
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )
    lines.append(f"- **Days in status:** {_fmt(days)}")
    if snapshot is not None:
        lines.append(f"- **Address:** {_fmt(snapshot.raw.get('primary_address'))}")
        lines.append(f"- **Type:** {_fmt(snapshot.permit_type)}")
        if snapshot.work_description:
            lines.append(f"- **Work described:** {snapshot.work_description}")
    lines.append(
        f"- **Record match:** "
        f"{MATCH_STATUS_LABELS.get(result.journey.match_status, result.journey.match_status.value)}"
    )
    lines.append("")

    lines.append("## Observed milestones")
    lines.append("")
    if snapshot is None:
        lines.append("No permit record was found to reconstruct a journey from.")
    else:
        milestones = []
        if snapshot.submitted_date:
            milestones.append(("Submitted", snapshot.submitted_date))
        milestones.append((f"Current status — {snapshot.status_desc}", snapshot.status_date))
        if snapshot.issue_date:
            milestones.append(("Issued", snapshot.issue_date))
        if snapshot.cofo_date:
            milestones.append(("Certificate of Occupancy issued", snapshot.cofo_date))
        for label, when in milestones:
            if when is not None:
                lines.append(f"- **{label}** — {_fmt(when)}")
    lines.append("")

    if result.journey.inspection_events:
        lines.append("## Inspections on record")
        lines.append("")
        lines.append("| Date | Type | Result |")
        lines.append("| --- | --- | --- |")
        for event in result.journey.inspection_events:
            lines.append(
                f"| {_fmt(event.inspection_date)} | {event.inspection_type} | "
                f"{event.inspection_result} |"
            )
        lines.append("")

    detections = result.stall_assessment.detections
    explanations = result.developer_explanations.explanations
    if detections:
        lines.append("## Findings")
        lines.append("")
        # Zipped 1:1, the same guarantee stall_findings.py relies on: Agent
        # 3 builds explanations by iterating detections in order.
        for detection, explanation in zip(detections, explanations):
            lines.append(
                f"### {CATEGORY_LABELS.get(detection.category, detection.category.value)} "
                f"— {SEVERITY_LABELS.get(detection.severity, detection.severity.value)}"
            )
            lines.append("")
            lines.append(f"**What the data shows.** {explanation.what_the_data_shows}")
            lines.append("")
            lines.append(f"**What this usually means.** {explanation.what_this_usually_means}")
            lines.append("")
            if explanation.developer_actionable_steps:
                lines.append("**Steps you can take**")
                for step in explanation.developer_actionable_steps:
                    lines.append(f"- {step.text}")
                lines.append("")
            if explanation.city_dependent_steps:
                lines.append("**Steps that depend on the city**")
                for step in explanation.city_dependent_steps:
                    lines.append(f"- {step.text}")
                lines.append("")
            if explanation.limitations:
                lines.append("**What this data cannot tell you**")
                for limitation in explanation.limitations:
                    lines.append(f"- {limitation}")
                lines.append("")

    if result.coverage_gaps or result.data_quality_flags:
        lines.append("## Coverage and data-quality notes")
        lines.append("")
        for gap in result.coverage_gaps:
            lines.append(f"- {gap}")
        for flag in result.data_quality_flags:
            lines.append(f"- {DATA_QUALITY_FLAG_LABELS.get(flag, flag.value)}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(result.developer_explanations.disclaimer)
    lines.append("")
    lines.append(_SOURCES_NOTE)
    lines.append("")

    return "\n".join(lines)


def render(result: PermitAnalysisResult) -> None:
    st.download_button(
        t("export.button"),
        data=build_report(result),
        file_name=f"permit-{result.permit_number}.md",
        mime="text/markdown",
        icon=":material/download:",
        help=t("export.help"),
    )
