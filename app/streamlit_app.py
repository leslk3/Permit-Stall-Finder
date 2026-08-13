"""Permit Stall Finder -- Streamlit MVP entrypoint.

Thin presentation layer over orchestration.pipeline.run_pipeline(). This
file and everything under app/ contain no analytical logic: no severity
computation, no cohort math, no knowledge-base matching, no explanation
text. Every fact rendered here already exists on the PermitAnalysisResult
returned by the orchestrator -- see research/UI_DESIGN.md for the original
design and the constraints each section renderer follows.

There is no persona/role gate: the landing page offers one unified way in
-- paste permit number(s), or search by address -- and the number of
permit numbers that resolve decides whether the user lands in the
single-permit deep-dive view or the portfolio.py triage table. A single
permit number always goes straight to the deep dive; two or more always
go to the table, with a selector to drill into any one of them. This
replaces an earlier persona-gated version of this file that asked "what
best describes you?" on first load -- removed because sorting by intent
(how many permits do you actually have in hand right now) is a more
direct signal than sorting by declared role.

Starred items and recent searches (storage/user_state.py, laid out by
sections/quick_access.py) exist for the same return user this whole page
is designed around: someone who checks the same permit(s) or address
every day for their job. Clicking a starred/recent pill below sets the
matching widget's session_state value *before* that widget is
instantiated later in this same script run -- the same pattern Streamlit
apps use to programmatically pre-fill a widget -- so a pill click behaves
exactly like the user having typed that value and clicked the tab's own
search/analyze button, with no extra st.rerun() required for the numbers
case. The "Clear results" button follows the same pre-widget-instantiation
rule in reverse: it blanks those same session_state keys and *does* call
st.rerun(), since clearing needs to also wipe already-rendered result
state below.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

import i18n
import portfolio
from db import get_connection, get_knowledge_base
from errors import safe_error_message, validate_permit_number
from sections import (
    address_search,
    coverage_gaps,
    disclaimer,
    export_report,
    location_map,
    next_best_action,
    permit_journey,
    quick_access,
    quick_glance,
    stall_findings,
)

from permit_stall_finder import config
from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, run_pipeline
from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.storage import user_state

_ASSETS_DIR = Path(__file__).parent / "assets"
_RASTER_LOGO_NAMES = ("logo.png", "logo.jpg", "logo.jpeg", "logo.webp")


def _logo_markup() -> str:
    """Markup for the hero logo, inlined rather than served through
    st.image() so it sits inside the hero's own centered markup block and
    is sized purely by CSS.

    A raster file dropped into app/assets/ (logo.png and friends) wins over
    the bundled vector fallback, so replacing the mark is a matter of
    saving a file rather than editing code. It is base64-embedded so it
    does not depend on Streamlit's static-file serving being enabled. The
    CSS box is square and the image is object-fit: cover, which
    centre-crops a non-square source instead of squashing it.

    Read once at import, not per rerun.
    """
    for name in _RASTER_LOGO_NAMES:
        candidate = _ASSETS_DIR / name
        if candidate.exists():
            suffix = candidate.suffix.lower()
            mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.lstrip('.')}"
            encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
            return f'<img src="data:{mime};base64,{encoded}" alt="Permit Stall Finder">'
    return (_ASSETS_DIR / "logo.svg").read_text()


_LOGO_MARKUP = _logo_markup()

st.set_page_config(
    page_title="Permit Stall Finder",
    page_icon="🌴",
    layout="wide",
    # Collapsed by default so the landing page is just the search box.
    # Saved/recent items live in the right-hand panel behind the built-in
    # sidebar toggle -- available in one click for the daily return user,
    # invisible to a first-time user who has no history to show.
    initial_sidebar_state="collapsed",
)

# Cosmetic only -- an accent bar that also carries the app's own title,
# instead of a separate thin decorative bar plus a full st.title() heading
# underneath it. Folding the title into the gradient bar (via a pure-CSS
# ::after label, since Streamlit's header has no built-in text slot)
# reclaims the vertical space a second heading row would cost --
# consistent with this page's "no scrolling" layout goal. Touches no
# analytical content or component structure; every fact still comes from
# PermitAnalysisResult exactly as the section renderers already display
# it. layout="wide" supports the quick-glance card and portfolio table
# sitting in a single horizontal strip without wrapping.
#
# position: relative (overriding Streamlit's default position: fixed) so
# the header scrolls away with the rest of the page instead of staying
# pinned/frozen at the top of the viewport. Once it's back in normal flow,
# margin-bottom on the header (rather than the earlier block-container
# padding-top hack, which existed only to keep content from hiding under
# a fixed header) is what creates breathing room before the page content.
#
# Palette: UCLA Anderson blue (#2774AE, with #003B5C for depth) on a warm
# Claude-style paper ground. UCLA gold appears only as the rule under the
# header and as the Elevated severity chip -- never as text or a button
# fill, because #FFD100 against this background is roughly 1.3:1 and
# unreadable. The gradient runs dark-to-mid blue rather than blue-to-gold
# so the centered white title keeps ~5:1 contrast across its whole width.
#
# Type: Inter stands in for Styrene (UI, labels, all tabular data, where
# scannability matters) and Source Serif 4 for Tiempos (title and intro
# prose, where the editorial warmth belongs). Both fall back to installed
# system faces, so the page still renders correctly with no network.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap');

    html, body, [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI',
                     Helvetica, Arial, sans-serif;
    }

    /* Streamlit draws its icons as ligatures in a Material Symbols font,
       so the blanket font-family rule above would render them as the
       literal word ("search"). Put their own font back. */
    [data-testid="stAppViewContainer"] span[data-testid="stIconMaterial"],
    [data-testid="stAppViewContainer"] .material-symbols-rounded,
    [data-testid="stAppViewContainer"] [class*="material-symbols"] {
        font-family: 'Material Symbols Rounded' !important;
    }

    /* Star fill. Material Symbols draws filled vs outline from a variable
       FILL axis defaulting to 0, so both states rendered hollow. Saved
       items get FILL 1 (solid); unsaved stay at 0 (outline, unfilled). */
    [class*="st-key-psf_star_on"] span[data-testid="stIconMaterial"] {
        font-variation-settings: 'FILL' 1 !important;
        color: #E0A800 !important;
    }
    [class*="st-key-psf_star_off"] span[data-testid="stIconMaterial"] {
        font-variation-settings: 'FILL' 0 !important;
    }

    /* Editorial serif, scoped to the title and the intro paragraph only --
       every number, label and table stays in the sans face. */
    [data-testid="stHeader"]::after,
    [data-testid="stAppViewContainer"] h1,
    [data-testid="stAppViewContainer"] h2,
    p.psf-intro {
        font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif !important;
    }

    /* The gradient bar and its CSS-drawn title are gone: the logo now
       carries the app's identity at the top of the page, so a second
       branded strip above it would just be chrome competing with the
       mark. What's left is a transparent strip holding the panel toggle. */
    [data-testid="stHeader"] {
        background: transparent !important;
        height: 3rem !important;
        position: relative !important;
        overflow: visible !important;
    }

    /* --- Centered measure -------------------------------------------
       layout="wide" is still needed so the quick-glance strip and the
       portfolio table get room, but a full-bleed text column at 1400px
       is unreadable. Capping the content and auto-margining it keeps
       everything on one centered axis. */
    div.block-container {
        max-width: 880px;
        margin: 0 auto;
        padding-top: 1rem !important;
    }

    /* --- Landing hero ------------------------------------------------ */
    .psf-hero {
        text-align: center;
        margin: 1.5rem 0 2rem;
    }
    /* Square by construction: a fixed box with the square-viewBox SVG
       filling it, so the mark can never be stretched by its container. */
    .psf-logo {
        width: 96px;
        height: 96px;
        margin: 0 auto 1.25rem;
        border-radius: 14px;
        overflow: hidden;
        line-height: 0;
    }
    .psf-logo svg,
    .psf-logo img {
        width: 100%;
        height: 100%;
        display: block;
        /* cover, not contain: a source that isn't square gets centre-
           cropped to the square box rather than letterboxed or squashed. */
        object-fit: cover;
    }
    .psf-hero h1 {
        font-size: 2.75rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        line-height: 1.15;
        margin: 0 0 0.75rem;
        color: #1F1E1D;
    }
    p.psf-intro {
        font-size: 1.08rem;
        line-height: 1.6;
        color: #56514B;
        max-width: 60ch;
        margin: 0 auto;
    }

    /* Center the search controls under the hero. Streamlit renders tab
       labels in a flex row, so justify-content is what centers them. */
    /* Icon-only submit: clip the label rather than hiding it, so the
       button keeps its accessible name while showing only the glyph.
       Covers the search trigger (now a plain button, matched by its key)
       as well as any form submit. */
    [data-testid="stFormSubmitButton"] button p,
    div[data-testid="stFormSubmitButton"] button p {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip: rect(0 0 0 0);
        white-space: nowrap;
    }
    [data-testid="stFormSubmitButton"] button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #2774AE !important;
        padding: 0.4rem !important;
        min-height: 0 !important;
    }
    [data-testid="stFormSubmitButton"] button:hover {
        background: #ECE8DF !important;
        color: #003B5C !important;
    }
    [data-testid="stFormSubmitButton"] span[data-testid="stIconMaterial"] {
        font-size: 1.5rem !important;
    }

    div[data-testid="stFormSubmitButton"] button {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: #2774AE !important;
        padding: 0.4rem !important;
        min-height: 0 !important;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        background: #ECE8DF !important;
        color: #003B5C !important;
    }
    div[data-testid="stFormSubmitButton"] button p,
    div[data-testid="stFormSubmitButton"] button div:not([data-testid="stIconMaterial"]) {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip: rect(0 0 0 0);
        white-space: nowrap;
    }
    div[data-testid="stFormSubmitButton"] span[data-testid="stIconMaterial"] {
        font-size: 1.5rem !important;
    }

    /* Streamlit's own "Press Enter to submit form" helper line stays
       hidden: the magnifying glass beside the field is the whole
       affordance, and Enter still submits whether or not it is captioned. */
    [data-testid="InputInstructions"] {
        display: none !important;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        flex: 0 0 auto;
    }
    div[data-testid="stTabs"] div[role="tablist"] {
        justify-content: center;
        gap: 1.5rem;
    }
    [data-testid="stTextInputRootElement"] input {
        text-align: center;
        font-size: 1.02rem;
    }

    /* --- Right-hand panel --------------------------------------------
       Streamlit only ships a left sidebar. The app view container is a
       flex row, so ordering the sidebar last moves the whole panel --
       and its built-in collapse control -- to the right edge, without
       reimplementing a fixed-position panel by hand. flex-shrink is the
       load-bearing part: without it the main column claims the whole row
       and squeezes the panel down to a sliver. */
    [data-testid="stSidebar"] {
        order: 2;
        flex-shrink: 0;
        border-right: none;
    }
    /* Streamlit hides the panel by translating it left by its own width,
       which is right for a left-hand sidebar but slides this one *into*
       the content as a visible sliver. Collapse it to zero width with no
       transform instead, and let the flex row reclaim the space. */
    [data-testid="stSidebar"][aria-expanded="false"] {
        width: 0 !important;
        min-width: 0 !important;
        transform: none !important;
        overflow: hidden;
        border-left: none;
    }
    [data-testid="stSidebar"][aria-expanded="true"] {
        width: 320px !important;
        min-width: 320px !important;
        transform: none !important;
        border-left: 1px solid #E6E2D9;
    }
    /* The reopen control is anchored top-left for a left sidebar; move it
       to the right edge so it sits on the side the panel now opens from.
       Its own expand/collapse glyph is left alone. */
    [data-testid="stExpandSidebarButton"] {
        position: fixed !important;
        right: 0.75rem;
        left: auto !important;
        top: 0.6rem;
        z-index: 1000;
    }
    section.stMain {
        order: 1;
    }

    /* Calmer rhythm: more air between lines, softer container edges. */
    [data-testid="stAppViewContainer"] p,
    [data-testid="stAppViewContainer"] li {
        line-height: 1.6;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }
    /* Hide the hamburger and Deploy affordances individually rather than
       hiding stToolbar wholesale -- the sidebar's reopen button is also a
       child of stToolbar, so hiding the container leaves the collapsed
       panel with no way back. */
    [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Session state defaults --------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "error" not in st.session_state:
    st.session_state.error = None
if "portfolio_rows" not in st.session_state:
    st.session_state.portfolio_rows = None
if "portfolio_results" not in st.session_state:
    st.session_state.portfolio_results = None
# "search" shows the landing page; "results" replaces it with the analysis
# view. A single script with a view switch rather than st.navigation pages:
# the two screens share the result in session_state and the right-hand
# panel, and st.navigation would add its own page nav into that same
# sidebar, competing with the saved/recent list already living there.
if "view" not in st.session_state:
    st.session_state.view = "search"

conn = get_connection()

# --- Quick access: starred + recent, for a return user checking the same
# permit(s) or address every day -- and a Clear results button beneath it
# so the same daily user can also blank today's search without a page
# reload. Both act by setting/clearing session_state keys *before* the
# widgets that own those keys are instantiated further down this script,
# rather than mutating already-rendered widgets.
#
# Both now live in the right-hand panel rather than stacked above the
# search box: they are return-user affordances, and on a first visit
# (nothing starred, nothing recent) they rendered as dead space directly
# between the title and the thing everyone actually came to do. -------
#
# 320px is right for a list of saved pills and far too narrow for the
# reader pane's contents -- the finding cards lay their metrics out in
# three columns and the map wants real width. Widened only on the results
# screen, where the panel is doing a different job.
if st.session_state.view == "results":
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"][aria-expanded="true"] {
            width: 560px !important;
            min-width: 560px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

with st.sidebar:
    # Language first: it reframes everything rendered after it, and this
    # widget writes st.session_state["language"], which i18n.t() reads. It
    # is instantiated before any translated string on the page below.
    # Language is a landing-page control: on the results screen the panel
    # is a reader pane, and a settings widget sitting on top of the
    # analysis is a different kind of thing from the analysis.
    #
    # The choice lives in i18n.LANGUAGE_STATE_KEY rather than in the
    # widget's own key. Streamlit discards keyed widget state on any run
    # where the widget is not drawn, so parking the value there would blank
    # it the first time the results screen rendered without the picker. The
    # on_change callback runs before the script body, so the copy across is
    # already done by the time anything below reads it -- assigning after
    # the widget call instead would leave every string on this run using
    # the previous language.
    if i18n.LANGUAGE_STATE_KEY not in st.session_state:
        st.session_state[i18n.LANGUAGE_STATE_KEY] = i18n.DEFAULT_LANGUAGE

    def _sync_language() -> None:
        picked = st.session_state.get("language_widget")
        if picked:
            st.session_state[i18n.LANGUAGE_STATE_KEY] = picked

    if st.session_state.view != "results":
        st.segmented_control(
            i18n.t("panel.language"),
            options=list(i18n.LANGUAGES),
            format_func=lambda code: i18n.LANGUAGES[code],
            default=st.session_state[i18n.LANGUAGE_STATE_KEY],
            key="language_widget",
            on_change=_sync_language,
        )
    # The panel carries different cargo on each screen. On the landing
    # page it is saved/recent -- the things that help you start a search.
    # On the results screen it becomes a reader pane holding the deep-dive
    # material that used to sit behind a "show full analysis" toggle in the
    # main column, so the long-form reading has its own column instead of
    # unrolling underneath the summary. Saved/recent is not shown there:
    # it is a way in, and on the results screen you are already in.
    # The reader pane is NOT rendered here. `with st.sidebar` can be
    # reopened anywhere in the script, and the pane has to be filled in
    # after the triage table has run: a table row click updates that
    # widget's selection state as the widget renders, which is further
    # down, so reading the selection this early showed the previously
    # selected permit's analysis -- the pane sat one click behind the
    # detail view beside it. It is rendered from the results section below
    # instead, once the selected permit is settled.
    qa_selection = None
    if st.session_state.get("view") != "results":
        st.markdown(f"### {i18n.t('panel.heading')}")
        # render() returns the clicked pill, which is None both when there
        # is no history and when there is history but nothing was clicked
        # -- so emptiness has to be read from storage, not inferred from
        # the return.
        has_history = bool(
            user_state.read_starred_items(conn) or user_state.read_recent_searches(conn)
        )
        qa_selection = quick_access.render(conn)
        if not has_history:
            st.caption(i18n.t("panel.empty"))

triggered = False
permit_numbers: list[str] = []

if qa_selection is not None:
    if qa_selection.kind == "permit_number":
        # Pre-fills the box for visibility, but also runs the pipeline
        # directly this same rerun -- a starred/recent permit pill is
        # meant to be a one-click re-run, not a one-click
        # pre-fill-then-still-have-to-click-Search.
        st.session_state["search_input"] = qa_selection.value
        triggered = True
        permit_numbers = [qa_selection.value]
    else:
        st.session_state["search_input"] = qa_selection.value
        address_search.run_query(conn, qa_selection.value)

# --- Search: one box for both permit numbers and addresses --------------
# Replaces the earlier two-tab layout. A user who has a permit number and
# a user who only has an address were being asked to classify their own
# input before typing it; the format of a permit number is distinctive
# enough (portfolio.looks_like_permit_number) to make that decision here
# instead. Every token has to look like a permit number for this to run
# the permit path -- a mixed or unrecognized entry is treated as an
# address, which is the safer fallback since the address lookup returns a
# pick-list rather than failing outright.
#
# A form rather than a bare input + button so Enter submits, the way any
# search field is expected to behave.
if st.session_state.view == "search":
    st.markdown(
        '<div class="psf-hero">'
        f'<div class="psf-logo">{_LOGO_MARKUP}</div>'
        f"<h1>{i18n.t('hero.title')}</h1>"
        f'<p class="psf-intro">{i18n.t("hero.subtitle")}</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    # Enter adds a term to a list instead of running the search. Building a
    # portfolio was previously a matter of knowing that commas worked --
    # nothing on screen said so, and one permit number per Enter is the
    # gesture people actually reach for. Search then runs the whole list at
    # once. A plain input with on_change rather than a form: a form defers
    # its widget's value until submit, so a user who typed a number and
    # clicked Search without pressing Enter first would have their text
    # silently dropped.
    if "pending_terms" not in st.session_state:
        st.session_state.pending_terms = []

    def _queue(raw: str) -> None:
        # Still splits commas: pasting a list someone sent you should work
        # the same as typing them one at a time.
        for token in portfolio.parse_permit_numbers(raw or ""):
            if token not in st.session_state.pending_terms:
                st.session_state.pending_terms.append(token)

    # The form holds the field and exactly one submit button, Add. That
    # single-button shape is load-bearing: Enter only submits a Streamlit
    # form when there is one submit button, so a second one inside the
    # form silently broke Enter entirely. Search therefore lives outside
    # the form, which is also what the flow wants -- Enter queues, Search
    # runs the queue.
    #
    # An earlier attempt used a bare input with an on_change callback.
    # That looked right and did nothing: on_change fires before the typed
    # value lands in session_state, so the handler read an empty string
    # every time. A form guarantees the value is committed by the time
    # its submit is handled.
    with st.form("search_form", border=False, clear_on_submit=True):
        field_col, add_col = st.columns([13, 1], vertical_alignment="center")
        with field_col:
            raw_text = st.text_input(
                "Permit number or address",
                placeholder=i18n.t("search.placeholder"),
                label_visibility="collapsed",
                key="search_input",
            )
        with add_col:
            add_clicked = st.form_submit_button(
                i18n.t("search.add"), icon=":material/add:"
            )

    if add_clicked:
        _queue(raw_text)

    st.caption(i18n.t("search.add_hint"))

    # Added terms, each removable. Rendered after the input so the list
    # reads as "what you have queued" rather than as part of the field.
    if st.session_state.pending_terms:
        chip_cols = st.columns(min(len(st.session_state.pending_terms), 4))
        for index, term in enumerate(list(st.session_state.pending_terms)):
            column = chip_cols[index % len(chip_cols)]
            if column.button(
                term, key=f"pending_{term}", icon=":material/close:", width="stretch"
            ):
                st.session_state.pending_terms.remove(term)
                st.rerun()

    # Outside the form, so it runs the queue rather than acting as a
    # second way to submit the field.
    search_clicked = st.button(
        i18n.t("search.submit"),
        icon=":material/search:",
        type="primary",
        key="run_search",
        disabled=not st.session_state.pending_terms,
    )

    if search_clicked:
        terms = list(st.session_state.pending_terms)
        if not terms:
            st.warning(i18n.t("search.empty"))
        elif all(portfolio.looks_like_permit_number(term) for term in terms):
            triggered = True
            permit_numbers = terms
        else:
            # A mixed or unrecognised list is treated as one address
            # lookup, which returns a pick-list rather than failing.
            address_search.run_query(conn, " ".join(terms))

    address_submitted, address_permit_numbers = address_search.render_matches(conn)
    if address_submitted:
        triggered = True
        permit_numbers = address_permit_numbers

# --- Run the pipeline: one permit goes straight to the deep dive, two or
# more go to the portfolio table. This is the only place that decision is
# made, regardless of which tab the permit numbers came from. -----------
if triggered:
    st.session_state.error = None
    if len(permit_numbers) == 1:
        permit_number, validation_error = validate_permit_number(permit_numbers[0])
        if validation_error:
            st.session_state.result = None
            st.session_state.error = validation_error
        else:
            try:
                with st.spinner(i18n.t("search.spinner")):
                    result = run_pipeline(conn, permit_number)
                if result.journey.match_status is MatchStatus.PERMIT_NOT_FOUND:
                    # A typo'd permit number used to land on a full result
                    # page reporting insufficient evidence, which reads as
                    # "nothing is known about your permit" rather than
                    # "that number doesn't exist". Offer near-matches to
                    # pick from instead, in the same list an ambiguous
                    # address already produces.
                    address_search.run_permit_suggestions(permit_number)
                    st.session_state.result = None
                    st.session_state.pending_terms = []
                    st.rerun()
                st.session_state.result = result
                st.session_state.portfolio_rows = None
                st.session_state.portfolio_results = None
                user_state.record_search(conn, "permit_number", permit_number)
            except PipelineExecutionError as exc:
                st.session_state.result = None
                st.session_state.error = safe_error_message(exc)
    else:
        batch = portfolio.run_batch(conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE)
        st.session_state.result = None
        st.session_state.portfolio_rows = batch.rows
        st.session_state.portfolio_results = batch.results_by_permit
        for permit_number in batch.results_by_permit:
            user_state.record_search(conn, "permit_number", permit_number)
        if batch.errors:
            st.warning(
                f"{len(batch.errors)} {i18n.t('results.batch_errors')} "
                + ", ".join(p for p, _ in batch.errors)
            )

    # A completed run leaves the landing page behind for the analysis
    # screen. The rerun is what makes it a page switch rather than a page
    # that grows: without it the hero and the search box stay rendered
    # above the results for the rest of this script run.
    if st.session_state.result is not None or st.session_state.portfolio_rows:
        st.session_state.view = "results"
        st.rerun()

if st.session_state.view != "results":
    st.stop()

# ======================= Results screen ================================
if st.button(i18n.t("results.back"), icon=":material/arrow_back:", key="back_to_search"):
    st.session_state.view = "search"
    st.session_state.result = None
    st.session_state.error = None
    st.session_state.portfolio_rows = None
    st.session_state.portfolio_results = None
    st.session_state.address_matches = None
    for key in list(st.session_state.keys()):
        if key.startswith("address_match_"):
            del st.session_state[key]
    st.rerun()

if i18n.current_language() != "en":
    st.caption(i18n.t("results.english_note"))

# --- Portfolio table, if a batch has been run ----------------------------
if st.session_state.portfolio_rows:
    portfolio.render_table(st.session_state.portfolio_rows)

    selected_permit = portfolio.selected_permit_number(st.session_state.portfolio_rows)
    cached_results = st.session_state.portfolio_results or {}
    if selected_permit and selected_permit in cached_results:
        # Reuses the PermitAnalysisResult already computed during the
        # batch run above -- never re-runs the pipeline just to render the
        # same permit's detail view a second time.
        st.session_state.result = cached_results[selected_permit]
        st.session_state.error = None

if st.session_state.error:
    st.error(st.session_state.error)

result = st.session_state.result
if result is not None:
    # Always visible, no scrolling required: the quick-glance strip, the
    # neutral top-level read, and a concrete next action. Deeper material
    # (the map, full journey, per-finding explanation cards,
    # coverage/data-quality notes) sits behind an explicit show/hide
    # toggle -- collapsed by default -- rather than always rendering a
    # long page. The disclaimer itself stays outside the toggle and always
    # renders, per UI_DESIGN.md's "never hide the disclaimer" decision.
    #
    # The map moved in behind the toggle: at 280px tall it was the largest
    # element on the page and sat directly above the verdict everyone came
    # for, pushing that verdict down. Where a permit is was never the
    # question this tool answers.
    # The permit number, the star control and the severity tally are all
    # inside quick_glance's bordered card now -- they were a caption, a
    # button and a separate coloured banner stacked underneath it, which
    # read as four unrelated blocks rather than one summary. That banner
    # was top_level_result's whole job, so it no longer renders here; the
    # card's own "Top finding"/"Result" cell carries the same headline,
    # and the per-finding detail is unchanged inside the toggle below.
    # Reopening the sidebar here, rather than in the panel block near the
    # top of this script, is what keeps the pane and the main column
    # showing the same permit: by this point the triage table has rendered
    # and its row selection is settled.
    with st.sidebar:
        st.markdown(f"### {i18n.t('panel.reader')}")
        # Starts at the journey: the map is in the main column beside the
        # summary, where where-it-is reads as part of the headline rather
        # than as the opening of a long-form read.
        permit_journey.render(result.journey)
        stall_findings.render(
            result.stall_assessment, result.developer_explanations, get_knowledge_base()
        )
        coverage_gaps.render(result.coverage_gaps, result.data_quality_flags)

    quick_glance.render(result, conn, compact=bool(st.session_state.portfolio_rows))
    location_map.render(result)
    next_best_action.render(result, get_knowledge_base())
    export_report.render(result)

    # The show/hide toggle is gone: that material now lives in the reader
    # pane rendered above. Streamlit has no API to open its sidebar
    # programmatically, so this is a pointer to the pane's own control
    # rather than a button that opens it -- without the line, the deep
    # dive would be a column the reader has no reason to know exists.
    st.caption(i18n.t("results.reader_hint"))

    disclaimer.render(result.developer_explanations.disclaimer)

