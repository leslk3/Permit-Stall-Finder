"""Tests for app/sections/export_report.py's report builder -- no
Streamlit involved, since build_report() is a pure function of an already
-complete PermitAnalysisResult.

The assertions worth having here are about what an exported file carries
once it leaves the app, not about exact prose: the disclaimer travels with
it, the generation time is stated, and every finding the screen shows is
in the document too. A report that quietly omits a severe finding, or that
loses the "not an official LADBS determination" line on the way to
someone's inbox, is the failure mode that matters.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sections import export_report  # noqa: E402

from permit_stall_finder.orchestration.pipeline import AnalysisOutcome  # noqa: E402
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus  # noqa: E402
from permit_stall_finder.schema.stall_detection import Severity, StallCategory  # noqa: E402

GENERATED_AT = datetime(2026, 8, 13, 17, 30, tzinfo=timezone.utc)
DISCLAIMER = (
    "This explanation is informational only and is not an official determination "
    "by the Los Angeles Department of Building and Safety (LADBS)."
)


def _step(text: str):
    return SimpleNamespace(text=text)


def _result(
    *,
    detections=(),
    explanations=(),
    coverage_gaps=(),
    data_quality_flags=(),
    inspection_events=(),
    outcome=AnalysisOutcome.STALL_DETECTED,
    snapshot_present=True,
):
    snapshot = (
        SimpleNamespace(
            status_desc="No Progress",
            permit_type="Bldg-Demolition",
            permit_sub_type=None,
            work_description="DEMO (E) SINGLE FAMILY DWELLING",
            submitted_date=date(2020, 1, 6),
            status_date=date(2020, 2, 11),
            issue_date=None,
            cofo_date=None,
            raw={"primary_address": "717 W 52ND PL"},
        )
        if snapshot_present
        else None
    )
    return SimpleNamespace(
        permit_number="20019-20000-00760",
        outcome=outcome,
        journey=SimpleNamespace(
            latest_snapshot=snapshot,
            match_status=MatchStatus.UNISSUED,
            inspection_events=list(inspection_events),
            derived=SimpleNamespace(days_submitted_to_current_status=2380),
        ),
        stall_assessment=SimpleNamespace(detections=list(detections)),
        developer_explanations=SimpleNamespace(
            explanations=list(explanations), disclaimer=DISCLAIMER
        ),
        coverage_gaps=list(coverage_gaps),
        data_quality_flags=list(data_quality_flags),
    )


def _detection(category=StallCategory.NO_INSPECTION_SINCE_ISSUANCE, severity=Severity.SEVERE):
    return SimpleNamespace(category=category, severity=severity)


def _explanation(**overrides):
    base = dict(
        what_the_data_shows="No inspection has been recorded since issuance.",
        what_this_usually_means="Work has typically not started on site.",
        developer_actionable_steps=[_step("Schedule a first inspection.")],
        city_dependent_steps=[_step("LADBS must assign an inspector.")],
        limitations=["Whether work has begun is not observable in this data."],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# --- what has to survive the trip -------------------------------------


def test_disclaimer_appears_and_is_agent_3s_own_wording():
    report = export_report.build_report(_result(), generated_at=GENERATED_AT)

    # Twice on purpose: at the top, where a forwarded document is read, and
    # at the end, where a reader who scrolls expects the fine print.
    assert report.count(DISCLAIMER) == 2


def test_report_states_when_it_was_generated_and_that_it_is_a_snapshot():
    report = export_report.build_report(_result(), generated_at=GENERATED_AT)

    assert "2026-08-13 17:30 UTC" in report
    assert "does not update" in report


def test_permit_number_is_the_title():
    report = export_report.build_report(_result(), generated_at=GENERATED_AT)

    assert report.startswith("# Permit 20019-20000-00760")


def test_summary_carries_status_days_and_address():
    report = export_report.build_report(_result(), generated_at=GENERATED_AT)

    assert "No Progress" in report
    assert "2380" in report
    assert "717 W 52ND PL" in report


# --- findings ----------------------------------------------------------


def test_every_finding_is_rendered_with_its_severity_and_explanation():
    result = _result(
        detections=[
            _detection(severity=Severity.SEVERE),
            _detection(
                category=StallCategory.REPEATED_CORRECTIONS, severity=Severity.WATCH
            ),
        ],
        explanations=[
            _explanation(),
            _explanation(what_the_data_shows="Corrections have been issued repeatedly."),
        ],
    )

    report = export_report.build_report(result, generated_at=GENERATED_AT)

    assert "Severe" in report
    assert "Watch" in report
    assert "No inspection has been recorded since issuance." in report
    assert "Corrections have been issued repeatedly." in report
    assert "Schedule a first inspection." in report
    assert "LADBS must assign an inspector." in report
    assert "Whether work has begun is not observable in this data." in report


def test_clean_permit_has_no_findings_section():
    report = export_report.build_report(
        _result(outcome=AnalysisOutcome.NO_MATERIAL_STALL_DETECTED),
        generated_at=GENERATED_AT,
    )

    assert "## Findings" not in report
    assert DISCLAIMER in report  # still travels with a clean report


# --- optional sections -------------------------------------------------


def test_inspection_events_render_as_a_table_when_present():
    result = _result(
        inspection_events=[
            SimpleNamespace(
                inspection_date=date(2022, 4, 13),
                inspection_type="Special/Order Compliance",
                inspection_result="Corrections Issued",
            )
        ]
    )

    report = export_report.build_report(result, generated_at=GENERATED_AT)

    assert "## Inspections on record" in report
    assert "2022-04-13" in report
    assert "Special/Order Compliance" in report


def test_coverage_and_data_quality_notes_are_included():
    result = _result(
        coverage_gaps=["No cohort was available for this permit type."],
        data_quality_flags=[DataQualityFlag.FIRST_OBSERVATION],
    )

    report = export_report.build_report(result, generated_at=GENERATED_AT)

    assert "## Coverage and data-quality notes" in report
    assert "No cohort was available for this permit type." in report
    assert "first time this tool has observed this permit" in report


def test_missing_permit_record_does_not_crash_the_report():
    report = export_report.build_report(
        _result(snapshot_present=False), generated_at=GENERATED_AT
    )

    assert "No permit record was found" in report
    assert DISCLAIMER in report
