"""Search-by-address -- an alternative to typing a permit number, for a
user who knows an address but not the permit number on it. A resolver
only: it never analyzes anything itself, it just helps a user find the
permit_number(s) to hand to the normal single-permit / portfolio flow in
streamlit_app.py, exactly the way parse_permit_numbers() hands typed text
to that same flow.

Calls ingestion.permits.fetch_permits_by_address() directly -- the same
kind of live network call run_pipeline() itself makes, just for a
different lookup. Every raw row it gets back is display-only here: no
analysis, no severity, no journey reconstruction -- selecting a result
below only queues its permit_number for the real pipeline to run.

Also records each successful search into storage/user_state.py's
search_history (so it shows up in quick_access.py's "Recent" row for a
return user). It deliberately offers no star of its own: these rows are a
disambiguation step, and starring belongs on a result once there is one
thing to star.
"""

from __future__ import annotations

import duckdb
import streamlit as st

from errors import GENERIC_ERROR_MESSAGE
from permit_stall_finder.ingestion.permits import (
    fetch_permit_suggestions,
    fetch_permits_by_address,
)
from permit_stall_finder.storage import user_state


def _format_match_label(row: dict) -> str:
    permit_nbr = row.get("permit_nbr") or "—"
    permit_type = row.get("permit_type") or "—"
    status_desc = row.get("status_desc") or "—"
    address = row.get("primary_address") or "—"
    return f"**{permit_nbr}** — {permit_type} — {status_desc} — {address}"


def run_query(conn: duckdb.DuckDBPyConnection, query: str) -> None:
    """Fetches permits for one address and parks them in session_state for
    render_matches() to draw. Split out from the rendering half so the
    single unified search box in streamlit_app.py can drive an address
    lookup without this module owning an input widget of its own."""
    cleaned = query.strip()
    if not cleaned:
        st.session_state.address_matches = None
        return
    try:
        st.session_state.address_matches = fetch_permits_by_address(cleaned)
        st.session_state.address_query_value = cleaned
        user_state.record_search(conn, "address", cleaned)
    except Exception:
        st.session_state.address_matches = None
        st.error(GENERIC_ERROR_MESSAGE)


def run_permit_suggestions(permit_number: str) -> None:
    """Looks for permits whose number merely *contains* what was typed,
    for when an exact lookup found nothing. Parked in session_state under
    the same key render_matches() already draws from, so a near-miss on a
    permit number lands in the same pick-list a partial address does --
    one "did you mean" list, not two that behave differently."""
    try:
        st.session_state.address_matches = fetch_permit_suggestions(permit_number)
        st.session_state.address_query_value = permit_number
    except Exception:
        st.session_state.address_matches = None
        st.error(GENERIC_ERROR_MESSAGE)


def render_matches(conn: duckdb.DuckDBPyConnection) -> tuple[bool, list[str]]:
    """Returns (submitted, permit_numbers). submitted is True only on the
    Streamlit run where the user just clicked "Analyze selected" --
    callers should treat submitted=False as "nothing to do yet", not as
    "the search found nothing"."""
    # No star here. These rows are a disambiguation step -- a list of
    # things that might be what you meant -- and offering to favourite the
    # query you are still in the middle of resolving asks the user to
    # commit to something they have not identified yet. Starring lives on
    # the result, once there is one thing to star.
    matches = st.session_state.get("address_matches")
    if matches is not None and not matches:
        st.info("No permits found for that address. Try a shorter or differently formatted address.")

    submitted = False
    selected: list[str] = []
    if matches:
        st.caption(f"{len(matches)} permit(s) found -- select which to analyze:")
        for row in matches:
            permit_nbr = row.get("permit_nbr")
            if not permit_nbr:
                continue
            if st.checkbox(_format_match_label(row), key=f"address_match_{permit_nbr}"):
                selected.append(permit_nbr)
        if selected:
            submitted = st.button("Analyze selected", type="primary", key="address_analyze_button")

    return submitted, selected
