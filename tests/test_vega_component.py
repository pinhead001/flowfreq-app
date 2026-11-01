"""Tests for the resizable-brush chart component (``vega_component``)."""

from __future__ import annotations

import re
from pathlib import Path

import altair as alt
import pandas as pd

import vega_component

HTML = (Path(vega_component.__file__).parent / "index.html").read_text(encoding="utf-8")


def _chart(rows: int) -> alt.Chart:
    data = pd.DataFrame({"x": range(rows), "y": range(rows)})
    brush = alt.selection_interval(encodings=["x"], name="period")
    return alt.Chart(data).mark_line().encode(x="x:Q", y="y:Q").add_params(brush)


def test_args_carry_the_spec_and_the_brushes_to_resize():
    args = vega_component.chart_args(_chart(3), resizable=["period"], height=300)
    assert args["resizable"] == ["period"] and args["height"] == 300
    assert args["spec"]["params"][0]["name"] == "period"
    assert re.fullmatch(r"[0-9a-f]{40}", args["spec_id"])


def test_a_daily_record_is_not_cut_at_altairs_row_limit():
    args = vega_component.chart_args(_chart(40_000))
    (rows,) = args["spec"]["datasets"].values()
    assert len(rows) == 40_000


def test_the_spec_id_changes_only_with_the_chart():
    """The browser redraws, and drops a dragged period, only when the chart changes."""
    a, b = vega_component.chart_args(_chart(3)), vega_component.chart_args(_chart(3))
    assert a["spec_id"] == b["spec_id"]
    assert vega_component.chart_args(_chart(4))["spec_id"] != a["spec_id"]


def test_args_are_plain_json():
    when = pd.DataFrame({"d": pd.to_datetime(["2020-01-01"]), "y": [1.0]})
    args = vega_component.chart_args(alt.Chart(when).mark_point().encode(x="d:T", y="y:Q"))
    (rows,) = args["spec"]["datasets"].values()
    assert isinstance(rows[0]["d"], str)


def test_scripts_are_pinned_with_sri():
    scripts = re.findall(r"<script src=\"([^\"]+)\"([^>]*)>", HTML)
    assert [Path(src).name for src, _ in scripts] == [
        "vega.min.js",
        "vega-lite.min.js",
        "vega-embed.min.js",
    ]
    for src, attrs in scripts:
        assert re.search(r"@\d+\.\d+\.\d+/", src), src  # an exact version
        assert src.startswith("vendor/"), src  # served next to index.html, not a CDN
        assert 'integrity="sha384-' in attrs and 'crossorigin="anonymous"' in attrs
    assert "cdn.jsdelivr.net" not in HTML


def test_bundled_scripts_match_their_integrity_hashes_and_carry_licences():
    import base64
    import hashlib

    root = Path(vega_component.__file__).parent
    for src, attrs in re.findall(r"<script src=\"([^\"]+)\"([^>]*)>", HTML):
        pinned = re.search(r'integrity="(sha384-[^"]+)"', attrs).group(1)
        digest = hashlib.sha384((root / src).read_bytes()).digest()
        assert pinned == "sha384-" + base64.b64encode(digest).decode(), src
        assert "University of Washington" in (root / src).with_name("LICENSE").read_text()


def test_vega_lite_matches_the_altair_schema():
    """The browser compiles the spec with the Vega-Lite version Altair wrote it for."""
    major_minor = ".".join(alt.SCHEMA_VERSION.lstrip("v").split(".")[:2])
    assert f"vega-lite@{major_minor}." in HTML


def test_the_grips_patch_names_vega_lites_brush_signals():
    """The patch depends on Vega-Lite's compiled names: <name>_x, <name>_brush, x(unit)."""
    for needle in (
        "`${name}_x`",
        '`event.item.mark.name !== "${name}_brush"`',
        "x(unit)",
        "ew-resize",
    ):
        assert needle in HTML, needle
