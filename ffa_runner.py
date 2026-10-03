"""
Display formatting for the Streamlit FFA app.

The analysis lives in :mod:`flowfreq.workflow`; this module turns its numbers
into the labelled, rounded, comma-separated strings a table wants. Nothing here
computes anything -- that separation is what lets the library serve consumers
that have no use for these column headings.
"""

from __future__ import annotations

import pandas as pd


def format_parameters_df(params: dict) -> pd.DataFrame:
    """Format analysis parameters as a single-row display DataFrame.

    Parameters
    ----------
    params : dict
        Parameters dict from run_ffa result.

    Returns
    -------
    pd.DataFrame
        Single-row DataFrame with formatted parameter values.
    """
    threshold = params.get("low_outlier_threshold", 0) or 0
    source = params.get("low_outlier_source", "MGBT")
    return pd.DataFrame(
        {
            "Mean (log10)": [_fmt_skew(params.get("mean_log", 0))],
            "Std Dev (log10)": [_fmt_skew(params.get("std_log", 0))],
            "Station Skew": [_fmt_skew(params.get("skew_station", 0))],
            "Weighted Skew": [_fmt_skew(params.get("skew_weighted", 0))],
            # None under station-skew-only: there is no regional skew to show.
            "Regional Skew": [_fmt_skew(params.get("regional_skew", 0))],
            "Skew Source": [skew_source_label(params)],
            "PILF Threshold (cfs)": [f"{threshold:,.0f} ({source})" if threshold > 0 else "none"],
            # peakfq's gbnlow: every row censored below the cut, gap years included.
            "PILFs": [f"{params.get('n_low_outliers', 0)}"],
            # The peaks MGBT itself flagged; differs from PILFs when gap years
            # or an override are in play.
            "MGBT Outliers": [_fmt_count(params.get("n_mgbt_outliers"))],
        }
    )


#: Display names for ``parameters["regional_skew_source"]`` (flowfreq's
#: ``SKEW_SOURCES``). "user" covers both a published study the app looked up
#: and a custom value typed in; the app records which in ``skew_note``.
SKEW_SOURCE_LABELS = {
    "user": "Regional (supplied)",
    "default": "Unsourced fallback -0.302",
    "station": "Station skew only",
}


def skew_source_label(params: dict) -> str:
    """Describe where the skew came from, for a table cell.

    Parameters
    ----------
    params : dict
        Parameters dict from run_ffa result. ``regional_skew_source`` is
        flowfreq's; ``skew_note``, when present, is the app's short note of the
        published study (or "custom value") behind a ``"user"`` skew.

    Returns
    -------
    str
        ``"n/a"`` for a result dict that predates the key.
    """
    raw = params.get("regional_skew_source")
    if raw is None:
        return "n/a"
    label = SKEW_SOURCE_LABELS.get(raw, str(raw))
    note = params.get("skew_note")
    return f"{label}: {note}" if note else label


def _fmt_skew(value: object) -> str:
    """Four decimals, or "none" for a missing value."""
    if value is None:
        return "none"
    return f"{float(value):.4f}"  # type: ignore[arg-type]


def _fmt_count(value: object) -> str:
    """An integer count, or "n/a" for a result dict that predates the key."""
    if value is None:
        return "n/a"
    return f"{int(value)}"  # type: ignore[call-overload]


def format_quantile_df(quantile_df: pd.DataFrame) -> pd.DataFrame:
    """Format quantile DataFrame for display.

    Parameters
    ----------
    quantile_df : pd.DataFrame
        Raw quantile DataFrame from run_ffa result.

    Returns
    -------
    pd.DataFrame
        Formatted DataFrame with comma-separated flows and percentage AEP.
    """
    df = quantile_df.copy()

    df["Return Interval (yr)"] = df["Return Interval (yr)"].apply(
        lambda x: "1.5" if x == 1.5 else f"{int(x)}"
    )

    df["AEP (%)"] = df["AEP (%)"].apply(lambda x: f"{x * 100:.1f}%")

    for col in ["Flow (cfs)", "Lower 90% CI", "Upper 90% CI"]:
        df[col] = df[col].apply(lambda x: f"{int(round(x)):,}")

    return df
