"""The StreamStats check and the ungaged page's banner. Nothing here reaches StreamStats."""

from __future__ import annotations

import pytest
import requests
from streamlit.testing.v1 import AppTest

import streamstats_health
import ungaged_ui

# The real check: conftest's autouse fixture replaces the module's name for it.
PROBE = streamstats_health.probe

CHECKED = "2026-11-15T14:05:00+00:00"


class _Response:
    def __init__(self, status_code, reason):
        self.status_code, self.reason, self.closed = status_code, reason, False

    def close(self):
        self.closed = True


def _answering(monkeypatch, status_code, reason):
    calls = []
    response = _Response(status_code, reason)

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(streamstats_health.requests, "get", get)
    return calls, response


def _failed(kind, detail="HTTP 403 Forbidden"):
    return {"ok": False, "kind": kind, "detail": detail, "checked": CHECKED}


def test_probe_success_is_one_small_request(monkeypatch):
    calls, response = _answering(monkeypatch, 200, "OK")
    out = PROBE()
    assert out["ok"] and out["kind"] == "ok" and out["detail"] == "HTTP 200 OK"
    assert response.closed
    ((url, kwargs),) = calls  # once, no retry
    assert url == "https://streamstats.usgs.gov/nssservices/regions"
    assert kwargs["timeout"] == streamstats_health.CHECK_TIMEOUT_S
    assert kwargs["stream"] is True  # the body is not downloaded
    assert kwargs["headers"]["User-Agent"].startswith("flowfreq")


@pytest.mark.parametrize(
    "code, reason, kind",
    [
        (403, "Forbidden", "refused"),
        (401, "Unauthorized", "refused"),
        (429, "Too Many Requests", "refused"),
        (500, "Internal Server Error", "error"),
        (503, "Service Unavailable", "error"),
        (404, "Not Found", "error"),
    ],
)
def test_probe_names_what_went_wrong(monkeypatch, code, reason, kind):
    calls, _ = _answering(monkeypatch, code, reason)
    out = PROBE()
    assert not out["ok"]
    assert out["kind"] == kind
    assert out["detail"] == f"HTTP {code} {reason}"
    assert len(calls) == 1  # a refusal is not retried


@pytest.mark.parametrize(
    "exc, detail",
    [
        (requests.ConnectTimeout("slow"), "no answer in 4 s"),
        (requests.ReadTimeout("slow"), "no answer in 4 s"),
        (requests.ConnectionError("no route"), "could not connect"),
    ],
)
def test_probe_never_raises(monkeypatch, exc, detail):
    def get(url, **kwargs):
        raise exc

    monkeypatch.setattr(streamstats_health.requests, "get", get)
    out = PROBE()
    assert out == {"ok": False, "kind": "unreachable", "detail": detail, "checked": out["checked"]}


def _counting(monkeypatch, answers):
    """Replace the check with one that gives ``answers`` in turn, and count the calls."""
    calls = []

    def probe(timeout=0.0):
        calls.append(1)
        return dict(answers[min(len(calls), len(answers)) - 1])

    monkeypatch.setattr(streamstats_health, "probe", probe)
    return calls


def test_status_is_kept_between_page_runs(monkeypatch):
    calls = _counting(monkeypatch, [_failed("refused")])
    first = streamstats_health.status()
    assert streamstats_health.status() == first == _failed("refused")
    assert len(calls) == 1


def test_status_checks_again_when_the_answer_is_old(monkeypatch):
    calls = _counting(monkeypatch, [_failed("refused")])
    clock = [1000.0]
    monkeypatch.setattr(streamstats_health.time, "monotonic", lambda: clock[0])
    streamstats_health.status()
    clock[0] += streamstats_health.CHECK_TTL_S - 1
    streamstats_health.status()
    assert len(calls) == 1
    clock[0] += 1
    streamstats_health.status()
    assert len(calls) == 2


def test_a_caller_cannot_change_the_kept_answer(monkeypatch):
    _counting(monkeypatch, [_failed("refused")])
    streamstats_health.status()["kind"] = "ok"
    assert streamstats_health.status()["kind"] == "refused"


@pytest.mark.parametrize(
    "kept, worked, checks",
    [
        ("refused", True, 2),  # a request worked while a failure was shown: look again
        ("ok", False, 2),  # a request failed while all looked well: look again
        ("refused", False, 1),  # agreement keeps the answer, and sends nothing
        ("ok", True, 1),
    ],
)
def test_note_drops_an_answer_the_page_has_contradicted(monkeypatch, kept, worked, checks):
    answer = {"ok": True, "kind": "ok", "detail": "", "checked": CHECKED}
    calls = _counting(monkeypatch, [answer if kept == "ok" else _failed(kept)])
    streamstats_health.status()
    streamstats_health.note(worked)
    streamstats_health.status()
    assert len(calls) == checks


def test_note_before_any_check_sends_nothing(monkeypatch):
    calls = _counting(monkeypatch, [_failed("refused")])
    streamstats_health.note(True)
    streamstats_health.note(False)
    assert not calls


def test_no_banner_when_streamstats_answers():
    assert streamstats_health.banner_text({"ok": True, "kind": "ok"}) == ""


@pytest.mark.parametrize(
    "kind, detail, said",
    [
        (
            "refused",
            "HTTP 403 Forbidden",
            "refusing requests from this server (HTTP 403 Forbidden)",
        ),
        ("error", "HTTP 503 Service Unavailable", "answering with an error (HTTP 503"),
        ("unreachable", "no answer in 4 s", "did not answer a check from this server (no answer"),
    ],
)
def test_banner_says_what_fails_and_what_still_works(kind, detail, said):
    text = streamstats_health.banner_text(_failed(kind, detail))
    assert said in text
    assert "**Delineate**" in text and "**Estimate**" in text
    assert "Basin characteristics (no StreamStats)" in text
    assert "Checked at 14:05 UTC" in text and "after 10 minutes" in text


def test_banner_without_a_time_still_reads():
    state = {"ok": False, "kind": "refused", "detail": "HTTP 403 Forbidden"}
    assert "Checked at a moment ago" in streamstats_health.banner_text(state)


def test_banner_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="kind='sideways'"):
        streamstats_health.banner_text({"ok": False, "kind": "sideways"})


def test_the_banner_names_the_form_as_the_page_does():
    # The banner points at an expander by its label; the label lives in ungaged_ui.
    import inspect

    assert 'st.expander("Basin characteristics (no StreamStats)"' in inspect.getsource(
        ungaged_ui._characteristics_form
    )


def _page():
    from ungaged_ui import render

    render()


def test_ungaged_page_warns_when_streamstats_refuses(monkeypatch):
    calls = _counting(monkeypatch, [_failed("refused")])
    at = AppTest.from_function(_page, default_timeout=30).run()
    assert not at.exception
    (warning,) = at.warning
    assert "StreamStats is refusing requests from this server (HTTP 403 Forbidden)" in warning.value
    at.run()  # a rerun shows the kept answer
    assert len(at.warning) == 1
    assert len(calls) == 1


def test_ungaged_page_has_no_banner_when_streamstats_answers():
    at = AppTest.from_function(_page, default_timeout=30).run()
    assert not at.exception
    assert not at.warning


def _raise(exc):
    def boom(*args, **kwargs):
        raise exc

    return boom


@pytest.mark.parametrize("run", ["estimate", "delineation"])
def test_a_failed_request_makes_the_page_look_again(monkeypatch, run):
    answer = {"ok": True, "kind": "ok", "detail": "", "checked": CHECKED}
    calls = _counting(monkeypatch, [answer, _failed("refused")])
    assert streamstats_health.status()["ok"]
    error = requests.HTTPError("403 Client Error: Forbidden")
    if run == "estimate":
        monkeypatch.setattr(ungaged_ui, "estimate_at_site", _raise(error))
        out = ungaged_ui.run_estimate(46.93, -113.97, "MT", None, False)
    else:
        monkeypatch.setattr(ungaged_ui, "delineate_watershed", _raise(error))
        out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out["kind"] == "network"
    assert streamstats_health.status()["kind"] == "refused"
    assert len(calls) == 2


def test_a_refusal_of_the_point_is_not_an_outage(monkeypatch):
    # StreamStats answered: it would not snap this point. The kept answer stands.
    answer = {"ok": True, "kind": "ok", "detail": "", "checked": CHECKED}
    calls = _counting(monkeypatch, [answer])
    streamstats_health.status()
    monkeypatch.setattr(ungaged_ui, "delineate_watershed", _raise(ValueError("no stream here")))
    assert ungaged_ui.run_delineation(46.93, -113.97, "MT")["kind"] != "network"
    streamstats_health.status()
    assert len(calls) == 1
