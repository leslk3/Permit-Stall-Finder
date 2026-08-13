"""Quick access -- starred permits/addresses and recent searches, shown
above the search tabs so a return user (someone checking the same
permit(s) every day for their job) can re-run yesterday's search in one
click instead of retyping it. Every value here comes straight from
storage/user_state.py; this module only lays out clickable pills and
reports which one (if any) was just clicked -- it never decides what to
do about that click. That decision (run a single permit directly, or
pre-fill and re-run an address search) belongs to streamlit_app.py, the
same "return the user's intent, let the entrypoint act on it" pattern
address_search.render() already follows.

render_star_toggle() is the other half of the same feature -- a small
star/unstar button placed next to whatever a user is currently looking
at (a single-permit result, or an address search query), so starring
something doesn't require a separate management screen for the common
case.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import streamlit as st

from i18n import t
from permit_stall_finder.storage import user_state


@dataclass(frozen=True)
class QuickAccessSelection:
    kind: str  # "permit_number" or "address"
    value: str


def _pill_icon(kind: str) -> str:
    return ":material/location_on:" if kind == "address" else ":material/description:"


def _pill_label(kind: str, value: str) -> str:
    return value


def _render_pill_row(
    items: list[tuple[str, str]], *, key_prefix: str
) -> QuickAccessSelection | None:
    """items is a list of (kind, value). Renders in rows of up to 4 so a
    longer list wraps instead of squeezing every pill into one row."""
    clicked: QuickAccessSelection | None = None
    # One per row now that these live in the 320px side panel rather than
    # across the full page width -- four columns there left no room for a
    # permit number to render on a single line.
    for kind, value in items:
        if st.button(
            _pill_label(kind, value),
            key=f"{key_prefix}_{kind}_{value}",
            icon=_pill_icon(kind),
            use_container_width=True,
        ):
            clicked = QuickAccessSelection(kind, value)
    return clicked


def render(conn: duckdb.DuckDBPyConnection) -> QuickAccessSelection | None:
    """Renders the starred + recent panel and returns the pill the user
    just clicked (if any) so streamlit_app.py can run it. Starred and
    recent are read fresh from storage on every run -- cheap local
    queries, not a network call, so there's no reason to cache them."""
    starred = user_state.read_starred_items(conn)
    recent = user_state.read_recent_searches(conn)

    # Don't repeat something in "recent" that's already pinned in
    # "starred" -- one line per thing a user is tracking, not two.
    starred_keys = {(item.kind, item.value) for item in starred}
    recent = [r for r in recent if (r.kind, r.value) not in starred_keys]

    if not starred and not recent:
        return None

    selection: QuickAccessSelection | None = None

    if starred:
        st.caption(f":material/star: {t('panel.starred')}")
        clicked = _render_pill_row(
            [(item.kind, item.value) for item in starred], key_prefix="qa_star"
        )
        selection = clicked or selection

        with st.expander(t("panel.manage")):
            for item in starred:
                label_col, action_col = st.columns([4, 1])
                label_col.write(_pill_label(item.kind, item.value))
                if action_col.button(t("panel.unstar"), key=f"qa_unstar_{item.kind}_{item.value}"):
                    user_state.unstar_item(conn, item.kind, item.value)
                    st.rerun()

    if recent:
        st.caption(f":material/history: {t('panel.recent')}")
        clicked = _render_pill_row(
            [(entry.kind, entry.value) for entry in recent], key_prefix="qa_recent"
        )
        selection = clicked or selection

    if starred or recent:
        st.divider()

    return selection


def render_star_toggle(conn: duckdb.DuckDBPyConnection, kind: str, value: str) -> None:
    """A single star/unstar button for one specific (kind, value) --
    dropped next to a single-permit result or an address search query so
    starring the thing you're already looking at takes one click.

    Icon-only: a filled star means saved, an outline means not, which is
    the whole state and needs no caption beside it. The label still exists
    for the accessible name and the hover tooltip -- it is the *visible*
    text that is gone, not the text. A toast confirms the write, because
    with the caption removed the only remaining feedback is the icon
    swapping, which is easy to miss on a page this dense.
    """
    starred = user_state.is_starred(conn, kind, value)
    label = t("star.added") if starred else t("star.add")
    icon = ":material/star:" if starred else ":material/star_outline:"
    if st.button("", key=f"star_toggle_{kind}_{value}", icon=icon, help=label):
        if starred:
            user_state.unstar_item(conn, kind, value)
            st.toast(t("star.removed_toast"), icon=":material/star_outline:")
        else:
            user_state.star_item(conn, kind, value)
            st.toast(t("star.added_toast"), icon=":material/star:")
        st.rerun()


def render_alert_toggle(conn: duckdb.DuckDBPyConnection, kind: str, value: str) -> None:
    """Bell beside the star: collects an email address to be told when this
    permit's status changes.

    The popover is explicit that nothing is sent yet, and that wording is
    load-bearing rather than decorative. There is no scheduler watching the
    source datasets and no mail transport in this codebase, so a
    subscription here is a recorded intent. Telling a user tracking a
    stalled permit that they will be alerted, when no alert can fire, would
    have them stop checking a permit nobody is watching for them -- a worse
    outcome than not offering the box at all. See
    user_state.subscribe_alert for the storage and privacy caveats.
    """
    existing = user_state.read_alert_subscriptions(conn, kind, value)
    icon = ":material/notifications_active:" if existing else ":material/notifications:"
    with st.popover("", icon=icon, help=t("alert.help")):
        st.markdown(f"**{t('alert.heading')}**")
        st.caption(t("alert.not_sending_yet"))

        if existing:
            st.caption(t("alert.existing"))
            for sub in existing:
                row_label, row_action = st.columns([3, 1])
                row_label.markdown(f"`{sub.email}`")
                if row_action.button(
                    t("alert.remove"), key=f"alert_rm_{kind}_{value}_{sub.email}"
                ):
                    user_state.unsubscribe_alert(conn, kind, value, sub.email)
                    st.toast(t("alert.removed_toast"), icon=":material/notifications_off:")
                    st.rerun()

        with st.form(f"alert_form_{kind}_{value}", border=False, clear_on_submit=True):
            email = st.text_input(
                t("alert.email_label"),
                placeholder="you@example.com",
                label_visibility="collapsed",
            )
            if st.form_submit_button(t("alert.submit"), icon=":material/notifications:"):
                try:
                    user_state.subscribe_alert(conn, kind, value, email)
                except ValueError:
                    st.error(t("alert.invalid_email"))
                else:
                    st.toast(t("alert.added_toast"), icon=":material/check_circle:")
                    st.rerun()
