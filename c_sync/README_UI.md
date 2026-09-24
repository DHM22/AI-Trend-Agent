# C-Sync interface

C-Sync is a Streamlit view of the AI Trend Agent's recorded run. It is based on
the SkillRadar UI by aldanah (imported unchanged in 61e97c4). It lives inside
this repo, and by default it reads the checkout it sits in. Set `CSYNC_BACKEND`
(or the older `SKILLRADAR_BACKEND`) to read another checkout.

It shows a **recorded run** (written by `02_src/demo_snapshot.py --capture`):
the snapshot at `SNAPSHOT_PATH` (default `01_data/demo_snapshot.json`) and the
signals file named by that snapshot's `source_signals`. It does not re-run any
agent and makes no API calls.

- Maturity is `evaluation.py`'s own `_maturity_score` applied to the stored
  confidence.
- Relevance is solved from the stored `total_score`
  (total = ½ maturity + ½ relevance).

## Layout

- **Left panel:** all pages. These are Home, Dashboard, Radar, Trend story,
  The gap, Evaluation, Decision and How it works. (The Curriculum page was
  removed: it repeated The gap.)
- **Top bar:** the five stages: 01 Discover, 02 Verify, 03 Compare, 04 Evaluate
  and 05 Decide. Each opens the page for that stage.
- **Home:** "From noise to curriculum". Each square is one pipeline stage, and
  its area is proportional to the real count for that stage. The stages are
  signals, then clusters, then assessed clusters, then recommendations, then
  actionable recommendations.
- **Dashboard:** every recommendation, most urgent tier first. You can filter by
  action, material type (lab or slides) and "actionable only".
- **Radar (01 Discover):** only the radar. A scanner beam sweeps it, and each
  signal flashes as the beam passes.
- **Trend story (02 Verify):** the evidence arrives one card at a time, and each
  card expands for its full note. GitHub cards show the repository's stars
  (⭐), taken from the recorded `github_lookup` note. The release check is green
  (✅) only when `verify_release` CONFIRMED the release.
- **Evaluation (04 Evaluate):** the scores stay hidden until you click "Reveal
  the scores", then fade in.
- **Decision (05 Decide):** the evidence chain is collapsed.

## Run

```powershell
python -m pip install -r c_sync/requirements-ui.txt
python -m streamlit run c_sync/app.py
```
