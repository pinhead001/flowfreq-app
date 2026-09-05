# Changelog

All notable changes to the FlowFreq app are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0]

First release as a standalone repository, split out of `pinhead001/hydrolib`.

### Changed
- The analysis code is now the separate
  [flowfreq](https://github.com/pinhead001/flowfreq) library, installed from a pinned tag.
  A library change reaches this app only when `requirements.txt` is bumped.
- Modules moved from `app/` to the repository root. Streamlit puts the script's own
  directory on `sys.path` and never the repository root, so the nested layout required a
  `sys.path.insert` hack to import its siblings; flattening makes the two the same
  directory and the hack is gone from all three files that carried it.
- `ffa_runner` is display formatting only. The analysis half it used to contain —
  `run_ffa`, `compute_skew_tables`, `build_skew_curves_dict` — moved into
  `flowfreq.workflow`, where a second consumer can reach it.

### Notes
- The app's version is a display string, not a release contract; it does not track the
  library's.
- Pre-split history is preserved in this repository and in the archived
  [pinhead001/hydrolib](https://github.com/pinhead001/hydrolib).
