# garmin-dashboard

A Garmin training dashboard ("Training Log") built as a Claude Data artifact.

- `install.ps1` is the one-command installer: it downloads the repository ZIP into %TEMP% and runs `setup.ps1`.
- `setup.ps1` runs on the user's Windows laptop: installs Python with uv, logs in to Garmin Connect,
  and schedules `scripts/garmin_export.py` to write JSON into Google Drive (`My Drive/garmin-dashboard`).
- `dashboard/index.html` and `dashboard/datasets.json` are the dashboard template.
- To build a dashboard for the user, follow `.claude/skills/garmin-dashboard/SKILL.md`.

The dashboard text is in English. Answer the user in their language.
