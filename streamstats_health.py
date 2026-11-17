"""Whether StreamStats is answering this server, shown on the ungaged page before a click.

Delineate and Estimate depend on StreamStats, and an outage or a refusal (it blocks an
address that has asked too much) used to show only after the click, as a failed request.
:func:`status` asks StreamStats one small question, the NSS region list, and
:func:`show` puts a warning on the page when the answer is not a plain success.

One request, one try, a short timeout, and the answer is kept for :data:`CHECK_TTL_S` for
every session on the server: the check never loops and never retries, so a refused server
does not earn itself a longer refusal. When one of the page's own requests disagrees with
the kept answer, the answer is dropped and the next run of the page checks again
(:func:`note`), so a warning does not outlive the outage by ten minutes, nor an outage
go unannounced for as long.

What it cannot see: the check asks the host the pour-point snap and the NSS services are
on, which every Delineate and Estimate starts with. The delineation itself runs on
per-region servers under that host, and one of those can be down while the check passes;
that still shows only as the failed request.

Only :func:`show` needs a Streamlit runtime.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import requests
import streamlit as st
from flowfreq.streamstats import GENERIC_HOST, USER_AGENT

logger = logging.getLogger(__name__)

#: How long one check's answer is shown before StreamStats is asked again, in seconds.
CHECK_TTL_S = 600
#: How long the check waits for StreamStats, in seconds. The page waits with it.
CHECK_TIMEOUT_S = 4.0
#: The request the check makes: the NSS region list, a small answer from the same host
#: the regression-region lookup and the pour-point snap use.
CHECK_URL = f"https://{GENERIC_HOST}/nssservices/regions"

#: Statuses that mean StreamStats is turning this server away, not failing.
_REFUSED = (401, 403, 429)

_lock = threading.Lock()
#: The last answer and when it stops being shown (``time.monotonic``), for every session.
_kept: Optional[Tuple[float, Dict[str, Any]]] = None

_WORKS_WITHOUT = (
    "Estimates from basin characteristics you enter (**Basin characteristics (no "
    "StreamStats)**, below) do not use StreamStats."
)


def probe(timeout: float = CHECK_TIMEOUT_S) -> Dict[str, Any]:
    """Ask StreamStats one question, once. Never raises.

    Parameters
    ----------
    timeout : float
        Seconds to wait for the answer.

    Returns
    -------
    dict
        ``ok`` (bool), ``kind`` (``"ok"``, ``"refused"``, ``"error"`` or ``"unreachable"``),
        ``detail`` (for example ``"HTTP 403 Forbidden"`` or ``"no answer in 4 s"``) and
        ``checked`` (the UTC time of the check, ISO 8601).
    """
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        # The body is not read: the status line is the answer.
        response = requests.get(
            CHECK_URL, timeout=timeout, stream=True, headers={"User-Agent": USER_AGENT}
        )
    except requests.Timeout:
        kind, detail = "unreachable", f"no answer in {timeout:g} s"
    except requests.RequestException as exc:
        logger.warning("StreamStats check failed: %s", exc)
        kind, detail = "unreachable", "could not connect"
    else:
        code = response.status_code
        detail = f"HTTP {code} {response.reason or ''}".strip()
        kind = "ok" if code < 400 else "refused" if code in _REFUSED else "error"
        response.close()
    if kind != "ok":
        logger.warning("StreamStats check: %s (%s)", kind, detail)
    return {"ok": kind == "ok", "kind": kind, "detail": detail, "checked": checked}


def status() -> Dict[str, Any]:
    """:func:`probe`, at most once per :data:`CHECK_TTL_S` for the whole server.

    Sessions that ask while a check is under way wait for its answer instead of sending
    their own.
    """
    global _kept
    with _lock:
        if _kept is None or time.monotonic() >= _kept[0]:
            _kept = (time.monotonic() + CHECK_TTL_S, probe())
        return dict(_kept[1])


def note(worked: bool) -> None:
    """Tell the check how one of the page's StreamStats requests went.

    A kept answer that disagrees is dropped, and the next :func:`status` checks again.
    The request's own outcome is not kept in its place: an estimate can succeed from
    the page's cache without StreamStats having answered anything.

    Parameters
    ----------
    worked : bool
        ``True`` for a request that succeeded, ``False`` for one StreamStats did not
        answer or turned away.
    """
    global _kept
    with _lock:
        if _kept is not None and _kept[1]["ok"] != worked:
            _kept = None


def forget() -> None:
    """Drop the kept answer, so the next :func:`status` checks again."""
    global _kept
    with _lock:
        _kept = None


def banner_text(state: Dict[str, Any]) -> str:
    """The warning for a check's answer, or ``""`` when StreamStats answered.

    Parameters
    ----------
    state : dict
        :func:`probe`'s result.

    Returns
    -------
    str

    Raises
    ------
    ValueError
        ``state`` has a ``kind`` :func:`probe` does not return.
    """
    kind = state.get("kind")
    if kind == "ok":
        return ""
    detail = state.get("detail", "")
    if kind == "refused":
        lead = (
            f"StreamStats is refusing requests from this server ({detail}), so **Delineate** "
            "and **Estimate** will fail until it lifts the refusal."
        )
    elif kind == "error":
        lead = (
            f"StreamStats is answering with an error ({detail}), so **Delineate** and "
            "**Estimate** are likely to fail."
        )
    elif kind == "unreachable":
        lead = (
            f"StreamStats did not answer a check from this server ({detail}), so "
            "**Delineate** and **Estimate** are likely to fail."
        )
    else:
        raise ValueError(f"not a StreamStats check result: kind={kind!r}")
    try:
        at = datetime.fromisoformat(state["checked"]).strftime("%H:%M UTC")
    except (KeyError, TypeError, ValueError):
        at = "a moment ago"
    return (
        f"{lead} {_WORKS_WITHOUT} Checked at {at}; it is checked again after "
        f"{CHECK_TTL_S // 60} minutes."
    )


def show() -> None:
    """Warn on the page when StreamStats is not answering this server."""
    text = banner_text(status())
    if text:
        st.warning(text)
