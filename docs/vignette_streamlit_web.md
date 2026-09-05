# Vignette: Deploy to Streamlit Community Cloud

Streamlit Community Cloud hosts public Streamlit apps from a public GitHub repository, free.
Deployment takes about five minutes.

## 1. Prerequisites

- A free account at [share.streamlit.io](https://share.streamlit.io)
- This repository, public, on GitHub
- The `flowfreq` tag in `requirements.txt` existing on the remote — the build fails at pip
  resolution otherwise:

```bash
git ls-remote --tags https://github.com/pinhead001/flowfreq | grep v0.3.0
```

## 2. What Cloud reads

Just `requirements.txt`, at the repository root, which is already here:

```
streamlit>=1.28.0
flowfreq @ git+https://github.com/pinhead001/flowfreq@v0.3.0
numpy>=1.20.0
pandas>=1.3.0
matplotlib>=3.4.0
scipy>=1.7.0
```

Streamlit Cloud installs git dependencies from this file with no extra configuration. There
is nothing to `pip install -e` — this repository is a deployed script, not a package, and
the analysis library comes from the pin.

No `packages.txt` is needed. The app requires no system libraries and no Fortran toolchain;
`flowfreq.peakfqr` is a build-it-yourself extension the app never touches.

## 3. Deploy

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub
2. **New app**
3. Set:
   - **Repository:** `pinhead001/flowfreq-app`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
4. **Deploy**

Cloud clones the repo, installs `requirements.txt`, and starts the app.

> **If you are moving an existing deployment here**, the main file path changes from
> `app/streamlit_app.py` to `streamlit_app.py` — the modules moved to the repository root.
> Missing this produces a build that succeeds and an app that cannot find its entry point.
> Some accounts do not allow repointing an existing app at a different repository; delete
> and recreate it in that case, setting the same custom subdomain to keep the URL.

## 4. Updating

Push to `main` and Cloud redeploys in about a minute. To pick up analysis changes, bump the
pinned tag in `requirements.txt` — the app is otherwise insulated from the library.

## 5. Secrets

None required. USGS NWIS is a public service and the app makes no authenticated calls. If
you add an authenticated service later, use Cloud's **Secrets** tab and read it via
`st.secrets`; never commit credentials.

## 6. Known limitations

- Community Cloud sleeps idle apps; the first request after a sleep is slow
- Memory is capped, so very long records or large batch runs may be tight
- The cold-start install compiles nothing, but cloning the pinned library adds a few seconds
