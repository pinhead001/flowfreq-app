# Vignette: Run the app locally

The FlowFreq Streamlit app (`streamlit_app.py`) is a browser-based interface for downloading
USGS streamflow data, running Bulletin 17C analysis, and exporting results.

## 1. Install

Python 3.10 or newer — Streamlit sets that floor.

```bash
git clone https://github.com/pinhead001/flowfreq-app
cd flowfreq-app

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

That installs Streamlit and, from a pinned git tag, the
[flowfreq](https://github.com/pinhead001/flowfreq) analysis library. Verify:

```bash
python -c "import streamlit, flowfreq; print('ready', flowfreq.__version__)"
```

## 2. Run

```bash
streamlit run streamlit_app.py
```

Or `make run`. Opens at <http://localhost:8501>.

The app's modules sit at the repository root, and Streamlit puts the script's own directory
on `sys.path`, so the imports resolve wherever you invoke it from — there is no
run-from-the-repo-root requirement.

```bash
# A different port, if 8501 is busy
streamlit run streamlit_app.py --server.port 8502
```

## 3. Using it

1. Enter a USGS site number (e.g. `03606500`, Big Sandy River at Bruceton, TN)
2. Set the regional skew and its standard error, or accept the B17C nationwide defaults
3. Download the peak-flow record
4. Run the analysis — EMA, falling back to Method of Moments if it does not converge
5. Compare station, weighted and regional skew curves
6. Export a ZIP of plots, frequency tables and fitted LP3 parameters

## 4. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: flowfreq` | The venv is not active, or `pip install -r requirements.txt` did not complete |
| `ModuleNotFoundError: ffa_runner` | You moved `streamlit_app.py` away from its siblings; they must stay in one directory |
| Pinned tag fails to install | Check the tag exists: `git ls-remote --tags https://github.com/pinhead001/flowfreq` |
| Port already in use | `streamlit run streamlit_app.py --server.port 8502` |
| An app call fails after bumping the pin | A `flowfreq` signature changed; `make test` reproduces it — that is what the import smoke test is for |

## 5. Updating the analysis library

`requirements.txt` pins a tag rather than tracking `main`, so a library change reaches this
app only when you bump it:

```
flowfreq @ git+https://github.com/pinhead001/flowfreq@v0.3.0
```

Land the change in `flowfreq`, tag a release there, bump that line, then run `make test`
before deploying.
