"""Moving between the app's pages.

``streamlit_app`` builds the pages with ``st.navigation`` and registers them here. The
page modules (``gage_ui``, ``ungaged_ui``) call :func:`go` to change page, so they need
neither import ``streamlit_app`` nor know how the pages are built.

Each page has its own URL path (``/``, ``/ungaged``, ``/gage``), which is what makes the
browser's Back and Forward buttons move between them.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping

import streamlit as st

#: The pages by the name a link gives them (``?page=<name>``).
PAGE_NAMES = ("flowfrequency", "ungaged", "gage")

#: Session key of the registered pages. Per session, not module state: a page module
#: run on its own (as its tests do) then finds none and takes the fallback in :func:`go`.
PAGES_KEY = "_nav_pages"


def register(pages: Mapping[str, Any]) -> None:
    """Record this run's pages, so that :func:`go` can switch to them.

    Parameters
    ----------
    pages : mapping
        Page name (one of :data:`PAGE_NAMES`) to the ``st.Page`` built for it.

    Raises
    ------
    ValueError
        If a name is not one of :data:`PAGE_NAMES`.
    """
    unknown = sorted(set(pages) - set(PAGE_NAMES))
    if unknown:
        raise ValueError(f"unknown page name(s) {unknown}; expected some of {PAGE_NAMES}")
    st.session_state[PAGES_KEY] = dict(pages)


def go(page: str, **query: str) -> None:
    """Switch to ``page`` in this tab and end the run.

    Must be called from the script body, not from a widget callback: Streamlit cannot
    switch pages inside a callback.

    Parameters
    ----------
    page : str
        One of :data:`PAGE_NAMES`.
    **query : str
        Query parameters for the page, such as ``site="12340500"`` for the gage page.

    Raises
    ------
    ValueError
        If ``page`` is not one of :data:`PAGE_NAMES`.
    """
    if page not in PAGE_NAMES:
        raise ValueError(f"unknown page {page!r}; expected one of {PAGE_NAMES}")
    pages: Dict[str, Any] = st.session_state.get(PAGES_KEY) or {}
    if page in pages:
        st.switch_page(pages[page], query_params=query or None)
    # No pages registered (a page module run by itself): leave a ?page= link in the URL,
    # which streamlit_app redirects to the page.
    st.query_params.from_dict({"page": page, **query})
    st.rerun()
