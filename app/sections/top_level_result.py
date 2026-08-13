"""Section B — top-level result. Same neutral visual treatment regardless
of outcome (UI_DESIGN.md decision 3): only the icon and text differ."""

from __future__ import annotations

import streamlit as st

from formatting import outcome_headline
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, PermitAnalysisResult

_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: ":material/check_circle:",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: ":material/help:",
    AnalysisOutcome.STALL_DETECTED: ":material/flag:",
}


def render(result: PermitAnalysisResult) -> None:
    icon = _ICONS[result.outcome]
    headline = outcome_headline(result)
    st.info(f"{icon}  **{headline}**")
