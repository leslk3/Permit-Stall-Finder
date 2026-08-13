"""UI string table and language selection.

Scope note, and it is a deliberate one: this translates the *interface* --
headings, labels, buttons, captions, the severity vocabulary Agent 2
assigns. It does not translate anything the pipeline produces. Agent 3's
explanations, the knowledge-base guidance, the LADBS contact block and,
most importantly, the disclaimer are rendered in English in both
languages.

That is not an oversight. Those strings are the grounded, citable half of
this tool: the disclaimer states the output is not an official LADBS
determination, and the explanations are tied to specific published
sources. Machine-translating compliance text into a language the sources
are not published in would mean showing a user a Spanish sentence that no
source actually supports. Translating that material is a content task for
a bilingual reviewer with the sources in hand, not a string-table task --
so the UI says plainly, in Spanish, that the analysis text stays in
English.

The Spanish here should be reviewed by a native speaker before this is
put in front of real users.
"""

from __future__ import annotations

import streamlit as st

DEFAULT_LANGUAGE = "en"
LANGUAGES: dict[str, str] = {"en": "English", "es": "Español"}

_STRINGS: dict[str, dict[str, str]] = {
    # --- Landing -------------------------------------------------------
    "hero.title": {
        "en": "Find your permit",
        "es": "Encuentre su permiso",
    },
    "hero.subtitle": {
        "en": (
            "Understand the observable journey of an LA building permit, identify unusual "
            "delays or process friction, and see grounded guidance on what may happen next. "
            "Search a permit number for a full deep-dive, several to triage a portfolio at "
            "once, or a street address if you don't have the number handy."
        ),
        "es": (
            "Comprenda el recorrido observable de un permiso de construcción de Los Ángeles, "
            "identifique demoras inusuales o fricción en el proceso, y vea orientación "
            "fundamentada sobre lo que puede ocurrir después. Busque un número de permiso "
            "para un análisis completo, varios para revisar una cartera a la vez, o una "
            "dirección si no tiene el número a mano."
        ),
    },
    "search.placeholder": {
        "en": "Permit number or street address",
        "es": "Número de permiso o dirección",
    },
    "search.submit": {"en": "Search", "es": "Buscar"},
    "search.empty": {
        "en": "Enter a permit number or a street address.",
        "es": "Ingrese un número de permiso o una dirección.",
    },
    "search.spinner": {"en": "Analysing permit...", "es": "Analizando el permiso..."},
    # --- Results -------------------------------------------------------
    "results.back": {"en": "New search", "es": "Nueva búsqueda"},
    "results.toggle": {
        "en": "Show full analysis (location, permit journey, finding-by-finding explanations, coverage notes)",
        "es": "Ver el análisis completo (ubicación, recorrido del permiso, explicación de cada hallazgo, notas de cobertura)",
    },
    "results.english_note": {
        "en": "",
        "es": (
            "El análisis, las explicaciones y el aviso legal se muestran en inglés: provienen "
            "de fuentes publicadas únicamente en ese idioma."
        ),
    },
    "results.batch_errors": {
        "en": "permit(s) couldn't be analyzed right now (the city's open data service may be temporarily unavailable) and are omitted below:",
        "es": "permiso(s) no se pudieron analizar en este momento (el servicio de datos abiertos de la ciudad puede no estar disponible) y se omiten a continuación:",
    },
    # --- Quick-glance card ---------------------------------------------
    "card.permit": {"en": "Permit number", "es": "Número de permiso"},
    "card.days": {"en": "Days in status", "es": "Días en este estado"},
    "card.top_finding": {"en": "Top finding", "es": "Hallazgo principal"},
    "card.result": {"en": "Result", "es": "Resultado"},
    "card.findings_info": {"en": "Finding breakdown", "es": "Desglose de hallazgos"},
    "card.no_findings": {
        "en": "No findings were raised for this permit.",
        "es": "No se generaron hallazgos para este permiso.",
    },
    # --- Star / panel ---------------------------------------------------
    "star.add": {"en": "Star this", "es": "Guardar"},
    "star.added": {"en": "Starred", "es": "Guardado"},
    "panel.heading": {"en": "Saved & recent", "es": "Guardados y recientes"},
    "panel.starred": {"en": "Starred", "es": "Guardados"},
    "panel.recent": {"en": "Recent", "es": "Recientes"},
    "panel.manage": {"en": "Manage starred", "es": "Administrar guardados"},
    "panel.unstar": {"en": "Unstar", "es": "Quitar"},
    "panel.empty": {
        "en": "Permits and addresses you search will collect here, and you can star the ones you check regularly.",
        "es": "Los permisos y direcciones que busque aparecerán aquí, y puede guardar los que consulte con frecuencia.",
    },
    "panel.language": {"en": "Language", "es": "Idioma"},
    # --- Severity vocabulary (Agent 2's own labels) ---------------------
    "severity.WATCH": {"en": "Watch", "es": "Observar"},
    "severity.ELEVATED": {"en": "Elevated", "es": "Elevado"},
    "severity.SEVERE": {"en": "Severe", "es": "Grave"},
    "severity.UNSCORED": {"en": "Unscored", "es": "Sin calificar"},
    "severity.count_one": {"en": "finding", "es": "hallazgo"},
    "severity.count_many": {"en": "findings", "es": "hallazgos"},
}


def current_language() -> str:
    """The active language code, defaulting to English. Read from
    session_state so every module resolves the same value within one
    script run without threading a parameter through every renderer."""
    lang = st.session_state.get("language", DEFAULT_LANGUAGE)
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str) -> str:
    """Looks up one UI string in the active language, falling back to
    English and then to the key itself -- a missing translation should
    degrade to a readable English string, never to a crash or a blank."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(current_language()) or entry.get(DEFAULT_LANGUAGE) or key


def severity_label(severity) -> str:
    """Translated name for a Severity enum member. Kept here rather than
    in formatting.py so formatting's SEVERITY_LABELS stays a pure,
    language-free mapping that the existing tests can keep asserting on."""
    return t(f"severity.{severity.name}")
