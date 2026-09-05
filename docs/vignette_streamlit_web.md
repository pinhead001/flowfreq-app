# Vignette: Deploy to Streamlit Community Cloud

Streamlit Community Cloud hosts public Streamlit apps from a public GitHub repository, free.

This vignette deploys a **second app alongside any existing one** and cuts over only once the
new deployment is proven. Nothing about the live app changes until you decide it should. If
you are deploying for the first time, the cut-over section simply does not apply.

## 1. Prerequisites

- A free account at [share.streamlit.io](https://share.streamlit.io)
- This repository, public, on GitHub
- The `flowfreq` tag named in `requirements.txt` existing on the remote — pip clones the
  dependency anonymously during the build, so a private library or a missing tag fails the
  deploy at dependency resolution:

```bash
git ls-remote --tags https://github.com/pinhead001/flowfreq | grep v0.3.0
```

## 2. What Cloud reads

Just `requirements.txt`, at the repository root:

```
streamlit>=1.28.0
flowfreq @ git+https://github.com/pinhead001/flowfreq@v0.3.0
numpy>=1.20.0
pandas>=1.3.0
matplotlib>=3.4.0
scipy>=1.7.0
```

Cloud installs git dependencies from this file with no extra configuration. There is nothing
to `pip install -e` — this repository is a deployed script, not a package, and the analysis
library comes from the pin.

No `packages.txt` is needed: no system libraries, and no Fortran toolchain. The
`flowfreq.peakfqr` extension is a build-it-yourself component the app never touches.

## 3. Deploy the new app

1. [share.streamlit.io](https://share.streamlit.io) → **Create app** → deploy from GitHub
2. Set:
   - **Repository:** `pinhead001/flowfreq-app`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **App URL:** a *temporary* subdomain, e.g. `flowfreq-app-test`
3. Open **Advanced settings** and set **Python 3.12**
4. **Deploy**

Two things are easy to get wrong here and expensive to undo.

**The Python version is fixed at creation.** Changing it later means deleting the app and
redeploying, which releases its URL in the process. The app needs 3.10 or newer because
Streamlit does, and 3.12 is the version CI actually validates — pick it explicitly rather
than accepting whatever the default happens to be.

**Use a throwaway subdomain.** A URL can only belong to one app, so claiming the real one now
would force you to take it from the live app before the new one is proven. That is the
cut-over, and it belongs at the end.

No secrets are needed. USGS NWIS is public and the app makes no authenticated calls.

## 4. Verify before cutting over

In the build log, watch for the line resolving `flowfreq @ git+…@v0.3.0`. That step is unique
to this deployment — the old app never had an external dependency to fetch — so it is where a
private repo, a missing tag or a typo in the pin will surface.

Then exercise the app for real. A page that loads is not evidence: Streamlit executes the
script on the first client connection, so anything past the imports only fails once you click
through.

- Analyse a known gage end to end — `03606500` (Big Sandy River at Bruceton, TN) is the
  fixture site the library's own tests use
- Check the frequency curve renders, with its confidence band
- Toggle between station, weighted and regional skew
- Download the ZIP and open it: plots, frequency table, fitted LP3 parameters
- Change an input, re-run, and confirm the numbers move in the direction they should — then
  set it back and confirm you get the **original** numbers again

That last check is worth its own line. An app that gives a different answer the second time
it is shown the same inputs has a state bug, and it is invisible unless you deliberately
return to a previous setting.

## 5. Cut over

Only once the new app is proven. The URL is the only thing the two deployments contend for:

1. **Old app** → Settings → clear or change its custom subdomain (or delete the app)
2. **New app** → Settings → claim that subdomain
3. Reload the URL and confirm it serves the new app

Nothing forces speed. The old app builds from `pinhead001/hydrolib`, whose `main` still
contains `app/` — the split's deletions went to this repository, never to that one — so the
old deployment keeps working indefinitely. Run both in parallel for as long as you want the
comparison.

**Archive `pinhead001/hydrolib` only after step 3.** Until then it is what the live
deployment builds from.

## 6. Updating

Push to `main` and Cloud redeploys in about a minute. To pick up analysis changes, bump the
pinned tag in `requirements.txt`; the app is otherwise insulated from the library.

## 7. Known limitations

- Community Cloud sleeps idle apps; the first request after a sleep is slow
- Memory is capped, so very long records or large batch runs may be tight
- An account can only run so many apps at once. If a new deploy is refused, that cap is the
  reason — delete a stale app rather than looking for a problem in this repository
- The cold-start install compiles nothing, but cloning the pinned library adds a few seconds
