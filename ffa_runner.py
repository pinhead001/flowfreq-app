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
            "Mean (log10)": [f"{params.get('mean_log', 0):.4f}"],
            "Std Dev (log10)": [f"{params.get('std_log', 0):.4f}"],
            "Station Skew": [f"{params.get('skew_station', 0):.4f}"],
            "Weighted Skew": [f"{params.get('skew_weighted', 0):.4f}"],
            "Regional Skew": [f"{params.get('regional_skew', 0):.4f}"],
            "PILF Threshold (cfs)": [f"{threshold:,.0f} ({source})" if threshold > 0 else "none"],
            "PILFs": [f"{params.get('n_low_outliers', 0)}"],
        }
    )


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
