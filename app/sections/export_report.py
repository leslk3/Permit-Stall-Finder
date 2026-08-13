"""Downloadable report of a completed analysis, for a user who wants to
forward what the tool found -- to a contractor, a client, or their own
inbox.

Same rule as every other module under app/: it composes no analysis. Every
line is a fact already on the PermitAnalysisResult, and it reuses
formatting.py's label maps rather than writing its own wording, so the
export and the screen never drift into describing the same finding
differently.

The document is assembled once, as a list of typed blocks, and rendered
twice -- to PDF for sending and to Markdown for anything that wants text.
Building each format from its own pass over the result is how two exports
of the same permit end up disagreeing, so there is one pass and two dumb
renderers. Blocks also make the content testable without parsing a PDF.

Two things about an exported file that do not apply to the page it came
from, and that shape what is here:

1. It travels. A download gets forwarded and read by people who never saw
   this app, so the disclaimer is embedded in the document itself rather
   than left behind on screen -- at the top, where a forwarded attachment
   is actually read, and again at the end. Agent 3's own disclaimer string
   is used, never a paraphrase.

2. It is a snapshot, not a feed. The permit keeps moving after the file is
   written, so the header states when it was generated and that it will
   not update; otherwise a month-old attachment reads as current status.

PDF is generated with reportlab -- pure Python, so it installs on a host
where system libraries cannot be added, which rules out the HTML-to-PDF
engines that need cairo or pango.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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

# Matches the app's own accent so a forwarded PDF still looks like it came
# from this tool.
_ACCENT = colors.HexColor("#2774AE")
_INK = colors.HexColor("#1F1E1D")
_MUTED = colors.HexColor("#56514B")
_CALLOUT_BG = colors.HexColor("#F0EEE6")


def _fmt(value: object) -> str:
    """Dates as ISO, None as an em dash. Nothing else is reformatted --
    numbers and source strings are carried through exactly as the pipeline
    produced them."""
    if value is None or value == "":
        return "—"
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def report_blocks(
    result: PermitAnalysisResult, *, generated_at: datetime | None = None
) -> list[tuple]:
    """The document as (kind, payload) blocks. Pure -- no Streamlit, and no
    clock unless one is injected, so a test can assert the whole structure."""
    now = generated_at or datetime.now(timezone.utc)
    snapshot = result.journey.latest_snapshot
    disclaimer = result.developer_explanations.disclaimer
    blocks: list[tuple] = [
        ("title", f"Permit {result.permit_number}"),
        ("disclaimer", disclaimer),
        (
            "meta",
            f"Generated {now.strftime('%Y-%m-%d %H:%M UTC')}. This is a snapshot and "
            "does not update -- re-run the tool for current status.",
        ),
        ("h2", "Summary"),
        ("kv", ("Result", outcome_headline(result))),
        ("kv", ("Status", _fmt(snapshot.status_desc if snapshot else None))),
    ]

    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )
    blocks.append(("kv", ("Days in status", _fmt(days))))
    if snapshot is not None:
        blocks.append(("kv", ("Address", _fmt(snapshot.raw.get("primary_address")))))
        blocks.append(("kv", ("Type", _fmt(snapshot.permit_type))))
        if snapshot.work_description:
            blocks.append(("kv", ("Work described", snapshot.work_description)))
    blocks.append(
        (
            "kv",
            (
                "Record match",
                MATCH_STATUS_LABELS.get(
                    result.journey.match_status, result.journey.match_status.value
                ),
            ),
        )
    )

    blocks.append(("h2", "Observed milestones"))
    if snapshot is None:
        blocks.append(("para", (None, "No permit record was found to reconstruct a journey from.")))
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
                blocks.append(("kv", (label, _fmt(when))))

    if result.journey.inspection_events:
        blocks.append(("h2", "Inspections on record"))
        blocks.append(
            (
                "table",
                (
                    ["Date", "Type", "Result"],
                    [
                        [_fmt(e.inspection_date), e.inspection_type, e.inspection_result]
                        for e in result.journey.inspection_events
                    ],
                ),
            )
        )

    detections = result.stall_assessment.detections
    explanations = result.developer_explanations.explanations
    if detections:
        blocks.append(("h2", "Findings"))
        # Zipped 1:1, the same guarantee stall_findings.py relies on: Agent
        # 3 builds explanations by iterating detections in order.
        for detection, explanation in zip(detections, explanations):
            category = CATEGORY_LABELS.get(detection.category, detection.category.value)
            severity = SEVERITY_LABELS.get(detection.severity, detection.severity.value)
            blocks.append(("h3", f"{category} — {severity}"))
            blocks.append(("para", ("What the data shows.", explanation.what_the_data_shows)))
            blocks.append(
                ("para", ("What this usually means.", explanation.what_this_usually_means))
            )
            if explanation.developer_actionable_steps:
                blocks.append(("h4", "Steps you can take"))
                blocks.append(
                    ("bullets", [s.text for s in explanation.developer_actionable_steps])
                )
            if explanation.city_dependent_steps:
                blocks.append(("h4", "Steps that depend on the city"))
                blocks.append(("bullets", [s.text for s in explanation.city_dependent_steps]))
            if explanation.limitations:
                blocks.append(("h4", "What this data cannot tell you"))
                blocks.append(("bullets", list(explanation.limitations)))

    if result.coverage_gaps or result.data_quality_flags:
        blocks.append(("h2", "Coverage and data-quality notes"))
        notes = list(result.coverage_gaps)
        notes += [
            DATA_QUALITY_FLAG_LABELS.get(f, f.value) for f in result.data_quality_flags
        ]
        blocks.append(("bullets", notes))

    blocks.append(("rule", None))
    blocks.append(("small", disclaimer))
    blocks.append(("small", _SOURCES_NOTE))
    return blocks


# --- Markdown ----------------------------------------------------------


def render_markdown(blocks: list[tuple]) -> str:
    lines: list[str] = []
    for kind, payload in blocks:
        if kind == "title":
            lines += [f"# {payload}", ""]
        elif kind == "disclaimer":
            lines += [f"> **{payload}**", ">"]
        elif kind == "meta":
            lines += [f"> {payload}", ""]
        elif kind == "h2":
            lines += [f"## {payload}", ""]
        elif kind == "h3":
            lines += [f"### {payload}", ""]
        elif kind == "h4":
            lines += [f"**{payload}**"]
        elif kind == "kv":
            label, value = payload
            lines.append(f"- **{label}:** {value}")
        elif kind == "para":
            lead, text = payload
            lines += [f"**{lead}** {text}" if lead else text, ""]
        elif kind == "bullets":
            lines += [f"- {item}" for item in payload] + [""]
        elif kind == "table":
            headers, rows = payload
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join("---" for _ in headers) + " |")
            lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
            lines.append("")
        elif kind == "rule":
            lines += ["---", ""]
        elif kind == "small":
            lines += [payload, ""]
    return "\n".join(lines)


def build_report(result: PermitAnalysisResult, *, generated_at: datetime | None = None) -> str:
    return render_markdown(report_blocks(result, generated_at=generated_at))


# --- PDF ---------------------------------------------------------------


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    common = dict(fontName="Helvetica", textColor=_INK, alignment=TA_LEFT, leading=14)
    return {
        "title": ParagraphStyle("psf_title", base, fontName="Helvetica-Bold", fontSize=18,
                                leading=22, textColor=_ACCENT, spaceAfter=10),
        "disclaimer": ParagraphStyle("psf_disc", base, fontName="Helvetica-Bold", fontSize=9,
                                     leading=12, textColor=_INK),
        "meta": ParagraphStyle("psf_meta", base, fontName="Helvetica", fontSize=8.5,
                               leading=11, textColor=_MUTED),
        "h2": ParagraphStyle("psf_h2", base, fontName="Helvetica-Bold", fontSize=13,
                             leading=16, textColor=_ACCENT, spaceBefore=14, spaceAfter=4),
        "h3": ParagraphStyle("psf_h3", base, fontName="Helvetica-Bold", fontSize=11,
                             leading=14, textColor=_INK, spaceBefore=10, spaceAfter=3),
        "h4": ParagraphStyle("psf_h4", base, fontName="Helvetica-Bold", fontSize=9.5,
                             leading=12, textColor=_INK, spaceBefore=6, spaceAfter=2),
        "body": ParagraphStyle("psf_body", base, fontSize=9.5, spaceAfter=4, **common),
        "small": ParagraphStyle("psf_small", base, fontName="Helvetica", fontSize=8,
                                leading=10, textColor=_MUTED, spaceAfter=4),
    }


def render_pdf(blocks: list[tuple], *, title: str = "Permit report") -> bytes:
    styles = _styles()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        title=title,
        author="Permit Stall Finder",
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
    )
    story: list = []

    for kind, payload in blocks:
        if kind == "title":
            story.append(Paragraph(escape(payload), styles["title"]))
        elif kind == "disclaimer":
            # A tinted, boxed cell rather than a plain paragraph: this is
            # the one line a forwarded document must not be skimmed past.
            cell = Paragraph(escape(payload), styles["disclaimer"])
            table = Table([[cell]], colWidths=[doc.width])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), _CALLOUT_BG),
                        ("BOX", (0, 0), (-1, -1), 0.75, _ACCENT),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story += [table, Spacer(1, 6)]
        elif kind == "meta":
            story += [Paragraph(escape(payload), styles["meta"]), Spacer(1, 4)]
        elif kind in ("h2", "h3", "h4"):
            story.append(Paragraph(escape(payload), styles[kind]))
        elif kind == "kv":
            label, value = payload
            story.append(
                Paragraph(f"<b>{escape(str(label))}:</b> {escape(str(value))}", styles["body"])
            )
        elif kind == "para":
            lead, text = payload
            body = f"<b>{escape(lead)}</b> {escape(text)}" if lead else escape(text)
            story.append(Paragraph(body, styles["body"]))
        elif kind == "bullets":
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(escape(str(i)), styles["body"])) for i in payload],
                    bulletType="bullet",
                    start="•",
                    leftIndent=14,
                )
            )
            story.append(Spacer(1, 4))
        elif kind == "table":
            headers, rows = payload
            data = [[Paragraph(f"<b>{escape(str(h))}</b>", styles["body"]) for h in headers]]
            data += [[Paragraph(escape(str(c)), styles["body"]) for c in row] for row in rows]
            table = Table(data, colWidths=[doc.width * w for w in (0.2, 0.45, 0.35)],
                          repeatRows=1)
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D3C8")),
                        ("BACKGROUND", (0, 0), (-1, 0), _CALLOUT_BG),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                )
            )
            story += [table, Spacer(1, 6)]
        elif kind == "rule":
            story += [Spacer(1, 8), HRFlowable(width="100%", color=colors.HexColor("#D9D3C8")),
                      Spacer(1, 6)]
        elif kind == "small":
            story.append(Paragraph(escape(payload), styles["small"]))

    doc.build(story)
    return buffer.getvalue()


def build_pdf(result: PermitAnalysisResult, *, generated_at: datetime | None = None) -> bytes:
    return render_pdf(
        report_blocks(result, generated_at=generated_at),
        title=f"Permit {result.permit_number}",
    )


def render(result: PermitAnalysisResult) -> None:
    st.download_button(
        t("export.button"),
        data=build_pdf(result),
        file_name=f"permit-{result.permit_number}.pdf",
        mime="application/pdf",
        icon=":material/download:",
        help=t("export.help"),
    )
