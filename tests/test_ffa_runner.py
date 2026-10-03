"""Tests for ffa_runner -- display formatting only.

The analysis these tables render moved to :mod:`flowfreq.workflow`; its tests
live in ``tests/test_workflow.py``. Nothing here calls into the library, which
is the point: this module must stay renderable without an analysis run.
"""

import pandas as pd

from ffa_runner import format_parameters_df, format_quantile_df


class TestFormatParametersDf:
    def test_format_parameters_df_columns(self):
        params = {
            "mean_log": 3.7173,
            "std_log": 0.2892,
            "skew_station": -0.1187,
            "skew_weighted": -0.1187,
            "regional_skew": -0.07,
            "regional_skew_source": "user",
            "skew_note": "WA Pacific Northwest study",
            "n_low_outliers": 2,
            "n_mgbt_outliers": 1,
        }
        df = format_parameters_df(params)
        expected_cols = [
            "Mean (log10)",
            "Std Dev (log10)",
            "Station Skew",
            "Weighted Skew",
            "Regional Skew",
            "Skew Source",
            "PILF Threshold (cfs)",
            "PILFs",
            "MGBT Outliers",
        ]
        assert list(df.columns) == expected_cols
        assert len(df) == 1

    def test_missing_pilf_keys_render_as_none(self):
        """Older result dicts have no PILF keys; the table must not blow up."""
        df = format_parameters_df({"mean_log": 3.7})
        assert df["PILF Threshold (cfs)"].iloc[0] == "none"
        assert df["PILFs"].iloc[0] == "0"

    def test_pilf_threshold_names_its_source(self):
        """A user needs to know whether the cut is MGBT's or their own."""
        mgbt = format_parameters_df(
            {"low_outlier_threshold": 1234.0, "n_low_outliers": 3, "low_outlier_source": "MGBT"}
        )
        assert mgbt["PILF Threshold (cfs)"].iloc[0] == "1,234 (MGBT)"
        assert mgbt["PILFs"].iloc[0] == "3"

        override = format_parameters_df(
            {"low_outlier_threshold": 500.0, "n_low_outliers": 1, "low_outlier_source": "override"}
        )
        assert override["PILF Threshold (cfs)"].iloc[0] == "500 (override)"


class TestSkewSourceColumns:
    def test_skew_source_names_the_study(self):
        df = format_parameters_df({"regional_skew_source": "user", "skew_note": "WA study"})
        assert df["Skew Source"].iloc[0] == "Regional (supplied): WA study"

    def test_station_only_has_no_regional_skew(self):
        """run_ffa returns regional_skew=None under station skew; it must not crash."""
        df = format_parameters_df({"regional_skew": None, "regional_skew_source": "station"})
        assert df["Regional Skew"].iloc[0] == "none"
        assert df["Skew Source"].iloc[0] == "Station skew only"

    def test_fallback_is_labelled_unsourced(self):
        df = format_parameters_df({"regional_skew_source": "default"})
        assert "Unsourced" in df["Skew Source"].iloc[0]

    def test_mgbt_outliers_shown_beside_pilfs(self):
        df = format_parameters_df({"n_low_outliers": 4, "n_mgbt_outliers": 2})
        assert df["PILFs"].iloc[0] == "4"
        assert df["MGBT Outliers"].iloc[0] == "2"

    def test_old_result_dicts_render(self):
        df = format_parameters_df({"mean_log": 3.7})
        assert df["Skew Source"].iloc[0] == "n/a"
        assert df["MGBT Outliers"].iloc[0] == "n/a"


class TestFormatQuantileDf:
    def test_format_quantile_df_formatting(self):
        raw = pd.DataFrame(
            {
                "Return Interval (yr)": [1.5, 2, 100],
                "AEP (%)": [0.667, 0.50, 0.01],
                "Flow (cfs)": [3957.5, 5284.4, 23158.7],
                "Lower 90% CI": [3000.0, 4000.0, 17000.0],
                "Upper 90% CI": [5000.0, 7000.0, 38000.0],
            }
        )
        df = format_quantile_df(raw)

        # Return intervals formatted correctly
        assert df["Return Interval (yr)"].iloc[0] == "1.5"
        assert df["Return Interval (yr)"].iloc[1] == "2"
        assert df["Return Interval (yr)"].iloc[2] == "100"

        # AEP as percentage
        assert df["AEP (%)"].iloc[2] == "1.0%"

        # Flow with commas
        assert df["Flow (cfs)"].iloc[2] == "23,159"
