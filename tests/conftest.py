"""Fixtures every test gets."""

from __future__ import annotations

import pytest

import streamstats_health


@pytest.fixture(autouse=True)
def _streamstats_answers(monkeypatch):
    """No test asks StreamStats whether it is up.

    The ungaged page checks on every run that has no kept answer, and a suite that did the
    same would send a request per page test and depend on the answer. The check is replaced
    with one that succeeds; a test of the banner replaces it again with the answer it wants.
    """
    ok = {"ok": True, "kind": "ok", "detail": "HTTP 200 OK", "checked": "2026-01-01T00:00:00+00:00"}
    monkeypatch.setattr(streamstats_health, "probe", lambda timeout=0.0: dict(ok))
    streamstats_health.forget()
    yield
    streamstats_health.forget()
