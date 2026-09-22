# SkillRadar AI interface

This Streamlit app reads the existing `AI-Trend-Agent` checkout. It does not
copy or modify any agent, fixture, or evaluation result. Its default backend
path is `C:\Users\ALD\Documents\AI-Trend-Agent`; set `SKILLRADAR_BACKEND` to
another checkout if needed.

The presentation follows **Discover → Verify → Compare → Evaluate → Decide**.
Home introduces the problem. Radar plots clickable nodes from saved trends.
Trend story shows original signals and verification notes. Curriculum previews
uploaded material. The gap compares a trend with its saved course citation.
Evaluation displays the original agent's scores. Decision shows the recorded
action and the evidence chain. How it works explains the process in plain
language. The top navigation and page CTAs preserve the selected trend.

## Run in VS Code PowerShell

```powershell
Set-Location 'C:\Users\ALD\Documents\ChatGPT\AITREND'
python -m pip install -r requirements-ui.txt
python -m streamlit run app.py
```

The pages replay `01_data/demo_snapshot.json` and `01_data/signals.json`
through the backend's existing loaders. Radar maturity badges and the
Evaluation page reconstruct saved `VerifiedTrend` and `CurriculumMatch` inputs
and call the original `EvaluationAgent.run`; the current recommendation calls
`RecommendationAgent.run`. The agents' built-in fallback rationale and action
plan are used in offline mode; no OpenAI or monitoring API request is made.
Current results can differ from the older recorded snapshot if the agent
implementation changed after capture; the UI keeps them labeled separately.

The Curriculum page can extract text from uploaded PDF, PPTX, and IPYNB files
through `curriculum_ingest`'s existing extractors. It does not index uploads or
claim they were compared to trends. The checkout's curriculum folders contain
no course files and no vector store. Live verification and curriculum search
require the existing backend's model/API setup and indexed course material;
those workflows are not exposed by this offline interface.
