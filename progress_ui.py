"""Progress indicators for the slow StreamStats steps: a watershed and frequency bars.

StreamStats takes 5-60 s to delineate a basin and compute its characteristics, and
``st.spinner`` says only that something is running. These show what is running: a
watershed whose boundary traces itself while the basin is delineated, and frequency bars
that rise in turn while the flood quantiles are estimated. Plain HTML and CSS, so no
component build; motion stops for users who ask for reduced motion.
"""

from __future__ import annotations

from contextlib import contextmanager
from html import escape
from typing import Any, Iterator

import streamlit as st

#: A basin outline that draws itself, its streams flowing to the outlet, and the outlet.
WATERSHED_SVG = """
<svg class="ff-shed" viewBox="0 0 64 64" aria-hidden="true">
  <path class="ff-shed-edge" d="M32 58 C20 56 9 47 8 35 C7 24 12 14 21 9 C28 5 38 5 45 9
    C54 14 58 25 56 36 C54 48 44 56 32 58 Z"/>
  <path class="ff-shed-stream" d="M32 56 L32 38 L22 24 M32 38 L43 22 M32 46 L18 38 M32 44 L47 36"/>
  <circle class="ff-shed-outlet" cx="32" cy="57" r="3"/>
</svg>
"""

#: Seven bars, tallest for the most frequent floods, rising one after another.
BARS_SVG = (
    '<svg class="ff-bars" viewBox="0 0 64 64" aria-hidden="true">'
    + "".join(
        f'<rect class="ff-bar" style="animation-delay:{i * 0.12:.2f}s" x="{4 + i * 8.5:.1f}" '
        f'y="{60 - h}" width="6" height="{h}" rx="1"/>'
        for i, h in enumerate((52, 44, 37, 30, 24, 18, 13))
    )
    + '<path class="ff-curve" d="M4 9 Q28 22 60 48"/></svg>'
)

STYLE = """
<style>
.ff-progress { display:flex; align-items:center; gap:14px; padding:10px 14px; margin:6px 0;
  border:1px solid rgba(128,128,128,.35); border-radius:8px; }
.ff-progress svg { width:44px; height:44px; flex:none; }
.ff-progress .ff-title { font-weight:600; }
.ff-progress .ff-detail { opacity:.8; font-size:.9em; }
.ff-shed-edge { fill:rgba(57,160,90,.12); stroke:#2e9e4f; stroke-width:2.5;
  stroke-dasharray:190; stroke-dashoffset:190; animation:ff-trace 2.4s ease-in-out infinite; }
.ff-shed-stream { fill:none; stroke:#3b82f6; stroke-width:2; stroke-linecap:round;
  stroke-dasharray:6 4; animation:ff-flow 1s linear infinite; }
.ff-shed-outlet { fill:#b45309; }
.ff-bar { fill:#3b82f6; transform-box:fill-box; transform-origin:bottom;
  animation:ff-rise 1.4s ease-in-out infinite; }
.ff-curve { fill:none; stroke:#b45309; stroke-width:2; stroke-dasharray:4 3; }
@keyframes ff-trace { 0% { stroke-dashoffset:190; } 60%,100% { stroke-dashoffset:0; } }
@keyframes ff-flow { to { stroke-dashoffset:-10; } }
@keyframes ff-rise { 0%,100% { transform:scaleY(.35); } 50% { transform:scaleY(1); } }
@media (prefers-reduced-motion: reduce) {
  .ff-shed-edge, .ff-shed-stream, .ff-bar { animation:none; stroke-dashoffset:0; }
}
</style>
"""

#: The graphics each step shows.
KINDS = {"delineate": (WATERSHED_SVG,), "estimate": (WATERSHED_SVG, BARS_SVG), "bars": (BARS_SVG,)}


def progress_html(kind: str, title: str, detail: str) -> str:
    """The indicator for ``kind`` ("delineate", "estimate" or "bars"), as HTML.

    Raises
    ------
    KeyError
        For an unknown ``kind``.
    """
    graphics = "".join(KINDS[kind])
    return (
        f'{STYLE}<div class="ff-progress" role="status">{graphics}<div>'
        f'<div class="ff-title">{escape(title, quote=False)}</div>'
        f'<div class="ff-detail">{escape(detail, quote=False)}</div></div></div>'
    )


@contextmanager
def working(kind: str, title: str, detail: str, where: Any = st) -> Iterator[None]:
    """Show the indicator while the block runs, then clear it.

    Parameters
    ----------
    kind : str
        See :func:`progress_html`.
    title, detail : str
        What is happening, in a line and a sentence.
    where : module or container
        Where to draw it: ``st`` (the main area) or a container.
    """
    slot = where.empty()
    slot.markdown(progress_html(kind, title, detail), unsafe_allow_html=True)
    try:
        yield
    finally:
        slot.empty()
