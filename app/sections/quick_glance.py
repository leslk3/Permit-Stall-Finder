"""Quick-glance horizontal summary card -- shown once at the top of a
completed single-permit analysis (below the persona switcher and any
portfolio table) so the highest-value facts are visible without
scrolling. Every field is read directly off an already-complete
PermitAnalysisResult; this module composes no new interpretation, only
lays out facts Agent 1/2/3 already produced across one row of
st.columns.

Deliberately separate from top_level_result.py (section B): that section
keeps the neutral, no-outcome-color-coding treatment UI_DESIGN.md decision
3 requires for the full-page summary. This card is a denser at-a-glance
strip meant to sit above it, not replace it -- the full section B/C/D/E/F/G
sequence still renders below for anyone who wants the complete picture.
"""

from __future__ import annotations

import streamlit as st

from formatting import SEVERITY_COLORS, SEVERITY_TEXT_COLORS, outcome_headline
from i18n import severity_label, t
from sections import quick_access
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, PermitAnalysisResult
from permit_stall_finder.schema.stall_detection import Severity

_OUTCOME_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: ":material/check_circle:",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: ":material/help:",
    AnalysisOutcome.STALL_DETECTED: ":material/flag:",
}

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.SEVERE: 3,
    Severity.ELEVATED: 2,
    Severity.WATCH: 1,
    Severity.UNSCORED: 0,
}


def _top_severity(result: PermitAnalysisResult) -> Severity | None:
    """Same plain max()-over-already-assigned-labels approach as
    portfolio._max_severity() -- kept as a small local copy rather than a
    cross-import so this card has no dependency on the portfolio module
    (it's also used from the single-permit view, which doesn't otherwise
    need portfolio.py at all)."""
    severities = [d.severity for d in result.stall_assessment.detections]
    if not severities:
        return None
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


def render(result: PermitAnalysisResult, conn) -> None:
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )
    severity = _top_severity(result)
    detections = result.stall_assessment.detections

    # Everything about the permit's headline state now lives inside this
    # one bordered box: the permit number, the star control and the
    # severity tally used to sit loose underneath it as a caption, a
    # button and a separate coloured callout, which read as four unrelated
    # blocks rather than one summary. The finding count carries an info
    # popover instead of a second full-width banner.
    with st.container(border=True):
        cols = st.columns([3, 2, 3, 2], vertical_alignment="top")
        cols[0].markdown(f"**{t('card.permit')}**  \n{result.permit_number}")
        cols[1].markdown(f"**{t('card.days')}**  \n{days if days is not None else '—'}")

        with cols[2]:
            if severity is not None:
                color = SEVERITY_COLORS[severity]
                text_color = SEVERITY_TEXT_COLORS[severity]
                at_top = sum(1 for d in detections if d.severity == severity)
                noun = t("severity.count_one") if at_top == 1 else t("severity.count_many")
                badge = (
                    f'<span style="background-color:{color};color:{text_color};'
                    f'padding:2px 10px;border-radius:4px;font-weight:600">'
                    f"{at_top} {severity_label(severity)} {noun}</span>"
                )
                st.markdown(f"**{t('card.top_finding')}**  \n{badge}", unsafe_allow_html=True)
                with st.popover("", icon=":material/info:"):
                    st.markdown(f"**{t('card.findings_info')}**")
                    for sev in (Severity.SEVERE, Severity.ELEVATED, Severity.WATCH, Severity.UNSCORED):
                        n = sum(1 for d in detections if d.severity == sev)
                        if n:
                            st.markdown(f"- {n} × {severity_label(sev)}")
            else:
                icon = _OUTCOME_ICONS[result.outcome]
                st.markdown(f"**{t('card.result')}**  \n{icon} {outcome_headline(result)}")

        # Star and bell share the last column as two icon controls side by
        # side: both are "do something about this permit" actions rather
        # than facts about it, so they read as a pair.
        with cols[3]:
            star_col, bell_col = st.columns(2)
            with star_col:
                quick_access.render_star_toggle(conn, "permit_number", result.permit_number)
            with bell_col:
                quick_access.render_alert_toggle(conn, "permit_number", result.permit_number)

