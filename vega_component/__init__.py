"""A build-less Vega-Lite component: an Altair chart whose brushes can be resized.

Streamlit's own ``st.altair_chart`` draws Vega-Lite as compiled, and a Vega-Lite interval
brush can only be drawn, slid and cleared: there is no way to drag one of its edges. This
component draws the same spec with vega-embed (bundled in ``vendor/`` as published, with
their SRI hashes and BSD-3 licences) and, before rendering, patches the compiled Vega so each
named interval selection on the x axis gets a grip at each end. Dragging a grip moves that
edge; dragging the box still slides it; double-clicking still clears it.

The component sends nothing back to Python: everything happens in the browser.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Sequence

import altair as alt
import streamlit.components.v1 as components

_component = components.declare_component("vega_chart", path=str(Path(__file__).parent))


def chart_args(
    chart: alt.TopLevelMixin, resizable: Sequence[str] = (), height: int = 400
) -> Dict[str, Any]:
    """The component's arguments for ``chart``.

    Parameters
    ----------
    chart : altair chart
        Any top-level Altair chart. Its data are inlined however many rows they have
        (Altair's default limit is 5,000, and a daily record runs to tens of thousands).
    resizable : sequence of str
        Names of interval selections on the x encoding to give edge grips.
    height : int
        Starting frame height in pixels; the frame then fits the drawn chart.

    Returns
    -------
    dict
        ``spec`` (the Vega-Lite dict), ``spec_id`` (a hash of it, so the browser redraws
        only when the chart changes), ``resizable`` and ``height``.
    """
    with alt.data_transformers.disable_max_rows():
        spec = chart.to_dict()
    text = json.dumps(spec, sort_keys=True, default=str)
    return {
        "spec": json.loads(text),
        "spec_id": hashlib.sha1(text.encode("utf-8")).hexdigest(),
        "resizable": list(resizable),
        "height": int(height),
    }


def vega_chart(
    chart: alt.TopLevelMixin, *, key: str, resizable: Sequence[str] = (), height: int = 400
) -> None:
    """Draw ``chart`` with resizable brushes (:func:`chart_args`)."""
    _component(**chart_args(chart, resizable, height), key=key, default=None)
