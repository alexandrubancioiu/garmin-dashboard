---
name: garmin-dashboard
description: Build the "Training Log" Garmin training dashboard for the person in their own Claude account, reading the files that setup.ps1 exports to their Google Drive. Use when they ask for their Garmin dashboard, "build my Garmin dashboard", "fă-mi panoul Garmin", or to reconnect the dashboard to new Drive files.
---

# Garmin dashboard

This repository's `setup.ps1` runs on the person's Windows laptop. It exports
their Garmin Connect data every few hours into Google Drive, in
`My Drive/garmin-dashboard/`: `activities.json`, `daily.json` and `status.json`,
each shaped `{"rows": [...], "meta": [...]}`. This skill builds the dashboard
that reads those files live through the person's Google Drive connector, so it
stays current with no further work from Claude.

Talk to the person in their language. The dashboard text is in English; if
they write in another language, offer once to translate the page's text.
Keep technical words out of what you tell them.

## 1. Check what is needed

- Google Drive tools (`search_files`, `download_file_content` of the Google
  Drive connector) must be loaded in this session. If they are not, ask the
  person to connect Google Drive at claude.ai/customize/connectors with the
  same Google account their laptop's Google Drive app uses, then to start a new
  session. Stop until they have.
- The Artifact tool must be available, since the dashboard is a Data artifact.

## 2. Find their files

1. `search_files` with
   `title = 'garmin-dashboard' and mimeType = 'application/vnd.google-apps.folder'`.
   If there are several, take the one whose files were modified most recently.
2. `search_files` with `parentId = '<folder id>'` and note the file ids of
   `activities.json`, `daily.json` and `status.json`.
3. If a file is missing, setup.ps1 has not run or Drive has not synced yet: ask
   the person to run `setup.ps1`, or wait a minute for Google Drive to sync, and
   look again.
4. `download_file_content` on `status.json` once, to confirm the connector can
   read it.

## 3. Create the dashboard

1. `Artifact` with `action: "quickstart"` and `intent: "other"`, then create
   the dashboard from the Dashboard ("Data") type it names, with the title
   `Training Log`. Follow the instructions that the create result
   carries: they are authoritative for how the store is written.
2. Write everything in one `ArtifactData` batch to the new artifact's url:
   - every document in `dashboard/datasets.json` (key `collection/doc_id`),
     replacing `ACTIVITIES_FILE_ID`, `DAILY_FILE_ID` and `STATUS_FILE_ID`
     with the ids from step 2;
   - `files/index.html` as `{"text": <the full contents of dashboard/index.html>}`.
   Do not change the page unless the person asks for a change.
3. Read `data/users/me` (`check`, `runs`) as the type instructions describe.
   On first open the page asks the person to allow Google Drive for this
   dashboard; until they do, the data shows as waiting, which is not a fault.
4. Offer once to pin it to their claude.ai sidebar.

## 4. Tell them

- The dashboard reads their Drive files each time it opens, also on the phone;
  the laptop exports every hour from 06:12 to 23:12, and a couple of minutes
  after they log on or unlock it.
- Readiness: if the watch computes Garmin Training Readiness, the dashboard
  shows Garmin's score; otherwise it shows its own estimate from sleep, HRV,
  Body Battery, resting heart rate and form, and says so on the card.
- The dashboard is private. Sharing its link shares their health data.
- If the data stops updating: the log is `%USERPROFILE%\garmin-dashboard\export.log`;
  Garmin tokens last about 6 months and are renewed by running
  `%USERPROFILE%\garmin-dashboard\.venv\Scripts\python.exe %USERPROFILE%\garmin-dashboard\garmin_login.py --force`.

## Changing the dashboard later

Read `files/index.html` from the artifact before any change, since the person
may have edited text on the page. The page follows the Data type's one-writer
rule: text known in advance is in the HTML, and everything the data decides is
drawn inside `data-draw` elements.
