# FlowFreq App

Interactive Streamlit web application for USGS streamflow retrieval and Bulletin 17C flood
frequency analysis.

Download annual peak flows for any USGS gage, run a Bulletin 17C analysis (EMA with a
Method-of-Moments fallback), compare station / weighted / regional skew options, and export
the results as a ZIP of plots, tables and fitted parameters.

The analysis itself lives in **[flowfreq](https://github.com/pinhead001/flowfreq)**, which
this app installs as a pinned dependency. This repository is the user interface.

## Run it locally

Python 3.10 or newer — Streamlit sets that floor.

```bash
git clone https://github.com/pinhead001/flowfreq-app
cd flowfreq-app
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Opens at <http://localhost:8501>. Or `make run`.

## What's here

| File | Purpose |
|------|---------|
| `streamlit_app.py` | The app. A top-level script, not a module with a `main()` |
| `ffa_runner.py` | Display formatting — turns analysis output into presentable tables |
| `ffa_export.py` | ZIP export: PNG plots, CSV tables, LP3 parameters |
| `requirements.txt` | Runtime dependencies, including the pinned `flowfreq` tag |

No analysis code. Bulletin 17C, EMA, MGBT, the USGS client and the frequency plot are all in
the library.

## Updating the library

`requirements.txt` pins a tag:

```
flowfreq @ git+https://github.com/pinhead001/flowfreq@v0.3.0
```

To pick up library changes: land them in `flowfreq`, tag a release there, then bump that
line. Pinning means an upstream regression cannot reach the deployed app on its own.

## Development

```bash
pip install black isort pytest
make check    # lint + tests, exactly what CI runs
make fmt      # apply formatting
```

The test suite imports the app, which in Streamlit's bare mode executes the whole script —
catching stale imports and, most usefully, any call that no longer matches a `flowfreq`
signature after a version bump.

## Deployment

Streamlit Community Cloud, from `main`, entry point `streamlit_app.py`. See
[docs/vignette_streamlit_web.md](docs/vignette_streamlit_web.md). No secrets required —
USGS NWIS is a public service.

## History

Both this repository and the library were split out of
[pinhead001/hydrolib](https://github.com/pinhead001/hydrolib), which holds the combined
pre-split history and is archived.

## License

MIT — see [LICENSE](LICENSE).
