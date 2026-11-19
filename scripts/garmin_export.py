"""Export Garmin Connect data for the "Training Log" dashboard.

Usage:
    python garmin_export.py [OUT_DIR] [--log LOG_FILE]

Writes three files into OUT_DIR (default: ~/garmin-dashboard):
    activities.json  activities from the last ACTIVITY_DAYS days
    daily.json       sleep, HRV, resting HR, stress, Body Battery and, on watches
                     that have it, Garmin Training Readiness
    status.json      today's training status, acute/chronic load and VO2max

Each file is {"rows": [...], "meta": [...]}. Days already downloaded are kept;
each run only asks Garmin for missing days and the last REFRESH_DAYS days, so it
stays well under Garmin's rate limits.

Logs in with the tokens saved by garmin_login.py (default ~/.garminconnect, or
the GARMINTOKENS environment variable). This uses the unofficial
python-garminconnect library, not an official Garmin API.
"""

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ACTIVITY_DAYS = 180  # history for the fitness / fatigue / form chart
DAILY_DAYS = 42      # days of sleep / HRV / resting HR
REFRESH_DAYS = 3     # the latest days are always fetched again (data fills in after a sync)
PAUSE = 0.6          # seconds between requests, to stay clear of 429 rate limits

TOKENS = os.environ.get("GARMINTOKENS", str(Path.home() / ".garminconnect"))


def g(obj, *path):
    """Read a nested field; None if anything on the way is missing."""
    for key in path:
        if isinstance(obj, dict):
            obj = obj.get(key)
        elif isinstance(obj, list) and isinstance(key, int) and -len(obj) <= key < len(obj):
            obj = obj[key]
        else:
            return None
        if obj is None:
            return None
    return obj


def num(value, digits=1):
    try:
        if value is None:
            return None
        if digits == 0:
            return int(round(float(value)))
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def sport_of(type_key):
    t = (type_key or "").lower()
    if "run" in t:
        return "run"
    if "swim" in t:
        return "swim"
    if "cycl" in t or "bik" in t or "ride" in t:
        return "bike"
    if "strength" in t or "fitness_equipment" in t or "hiit" in t or "cardio" in t:
        return "strength"
    if "walk" in t or "hik" in t:
        return "walk"
    return "other"


def activity_row(a):
    start = a.get("startTimeLocal") or ""
    type_key = g(a, "activityType", "typeKey")
    return {
        "id": str(a.get("activityId")),
        "date": start[:10],
        "start": start[11:16],
        "name": a.get("activityName"),
        "type": type_key,
        "sport": sport_of(type_key),
        "duration_min": num((a.get("duration") or 0) / 60),
        "moving_min": num((a.get("movingDuration") or 0) / 60) or None,
        "distance_km": num((a.get("distance") or 0) / 1000, 2) or None,
        "avg_speed": num(a.get("averageSpeed"), 3),
        "avg_hr": num(a.get("averageHR"), 0),
        "max_hr": num(a.get("maxHR"), 0),
        "calories": num(a.get("calories"), 0),
        "load": num(a.get("activityTrainingLoad"), 0),
        "te_aerobic": num(a.get("aerobicTrainingEffect")),
        "te_anaerobic": num(a.get("anaerobicTrainingEffect")),
        "elevation_m": num(a.get("elevationGain"), 0),
        "vo2max": num(a.get("vO2MaxValue"), 0),
    }


class RateLimited(Exception):
    pass


def call(label, fn, *args):
    """One request to Garmin; a 429 stops the run, other errors give None."""
    from garminconnect import GarminConnectTooManyRequestsError

    time.sleep(PAUSE)
    try:
        return fn(*args)
    except GarminConnectTooManyRequestsError as exc:
        raise RateLimited(str(exc)) from exc
    except Exception as exc:  # one day without data must not stop the export
        print(f"  ! {label}: {exc}")
        return None


class Readiness:
    """Garmin Training Readiness, only on watches that compute it.

    The first two days asked tell whether this watch sends it at all; if both are
    empty the rest of the run skips the request (Forerunner 255 and older).
    """

    def __init__(self):
        self.tried = 0
        self.seen = False

    def get(self, api, day):
        if not self.seen and self.tried >= 2:
            return {}
        self.tried += 1
        data = call(f"readiness {day}", api.get_morning_training_readiness, day) or {}
        if data.get("score") is not None:
            self.seen = True
        return data


def daily_row(api, day, readiness):
    stats = call(f"stats {day}", api.get_stats, day) or {}
    sleep = call(f"sleep {day}", api.get_sleep_data, day) or {}
    hrv = call(f"hrv {day}", api.get_hrv_data, day) or {}
    ready = readiness.get(api, day)

    sleep_dto = sleep.get("dailySleepDTO") or {}
    hrv_sum = hrv.get("hrvSummary") or {}
    secs = sleep_dto.get("sleepTimeSeconds")
    stress = stats.get("averageStressLevel")
    return {
        "date": day,
        "readiness": num(ready.get("score"), 0),
        "readiness_level": ready.get("level"),
        "sleep_score": num(g(sleep_dto, "sleepScores", "overall", "value"), 0),
        "sleep_h": num(secs / 3600, 2) if secs else None,
        "deep_h": num((sleep_dto.get("deepSleepSeconds") or 0) / 3600, 2) if secs else None,
        "rem_h": num((sleep_dto.get("remSleepSeconds") or 0) / 3600, 2) if secs else None,
        "hrv": num(hrv_sum.get("lastNightAvg"), 0),
        "hrv_week": num(hrv_sum.get("weeklyAvg"), 0),
        "hrv_status": hrv_sum.get("status"),
        "rhr": num(stats.get("restingHeartRate") or sleep.get("restingHeartRate"), 0),
        "stress_avg": num(stress, 0) if stress is not None and stress >= 0 else None,
        "bb_now": num(stats.get("bodyBatteryMostRecentValue"), 0),
        "bb_high": num(stats.get("bodyBatteryHighestValue"), 0),
        "bb_low": num(stats.get("bodyBatteryLowestValue"), 0),
    }


def status_row(api, day):
    st = call("training status", api.get_training_status, day) or {}
    latest = g(st, "mostRecentTrainingStatus", "latestTrainingStatusData") or {}
    devices = [d for d in latest.values() if isinstance(d, dict)]
    dev = next((d for d in devices if d.get("primaryTrainingDevice")), devices[0] if devices else {})
    acute = dev.get("acuteTrainingLoadDTO") or {}
    vo2 = g(st, "mostRecentVO2Max", "generic") or {}
    return {
        "date": day,
        "training_status": dev.get("trainingStatusFeedbackPhrase"),
        "acute_load": num(acute.get("dailyTrainingLoadAcute"), 0),
        "chronic_load": num(acute.get("dailyTrainingLoadChronic"), 0),
        "acwr": num(acute.get("dailyAcuteChronicWorkloadRatio"), 2),
        "acwr_status": acute.get("acwrStatus"),
        "vo2max": num(vo2.get("vo2MaxPreciseValue") or vo2.get("vo2MaxValue")),
    }


def save(out, name, rows, note):
    doc = {
        "rows": rows,
        "meta": [
            {"label": "Exported", "value": datetime.now(timezone.utc).isoformat(timespec="seconds")},
            {"label": "Contents", "value": note},
            {"label": "Script", "value": "garmin_export.py from github.com/alexandrubancioiu/garmin-dashboard"},
        ],
    }
    # Write in place, so Google Drive keeps the same file id.
    (out / name).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def load_rows(out, name):
    try:
        return json.loads((out / name).read_text(encoding="utf-8")).get("rows") or []
    except (OSError, ValueError):
        return []


def report(name, rows):
    print(f"\n{name}: {len(rows)} rows")
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    for key in keys:
        filled = sum(1 for r in rows if r.get(key) not in (None, ""))
        print(f"  {key:<16} {filled:>4} / {len(rows)}")


def main():
    parser = argparse.ArgumentParser(description="Export Garmin data for the Training Log dashboard.")
    parser.add_argument("out", nargs="?", default=str(Path.home() / "garmin-dashboard"), help="folder to write the files to")
    parser.add_argument("--log", help="write messages to this file (for scheduled runs without a window)")
    parser.add_argument("--min-interval", type=int, default=0, metavar="MINUTES",
                        help="skip the run if the last export finished less than this many minutes ago")
    args = parser.parse_args()

    # Scheduled runs also start on every unlock and logon; this keeps them from
    # asking Garmin for the same data again within a few minutes.
    stamp = Path(__file__).with_name("last_export.txt")
    if args.min_interval:
        try:
            last = datetime.fromisoformat(stamp.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            last = None
        if last and datetime.now(timezone.utc) - last < timedelta(minutes=args.min_interval):
            if args.log:
                with open(args.log, "a", encoding="utf-8") as log:
                    log.write(f"Skipped at {datetime.now().isoformat(timespec='seconds')}: the last export was less than {args.min_interval} minutes ago.\n")
            return 0

    if args.log:
        log = open(args.log, "w", encoding="utf-8")
        sys.stdout = sys.stderr = log
        print(f"Started at {datetime.now().isoformat(timespec='seconds')}")

    from garminconnect import Garmin

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    api = Garmin()
    api.login(TOKENS)
    print(f"Logged in. Exporting to {out}")

    today = date.today()
    rate_limited = False

    # Activities: a single paged request for the whole period.
    start = (today - timedelta(days=ACTIVITY_DAYS)).isoformat()
    acts = api.get_activities_by_date(start, today.isoformat())
    activities = sorted((activity_row(a) for a in acts), key=lambda r: (r["date"], r["start"]), reverse=True)
    save(out, "activities.json", activities, f"Garmin activities from the last {ACTIVITY_DAYS} days")

    # Daily values: keep what we have, ask only for missing days and the last REFRESH_DAYS.
    known = {r["date"]: r for r in load_rows(out, "daily.json")}
    days = [(today - timedelta(days=i)).isoformat() for i in range(DAILY_DAYS)]
    recent = (today - timedelta(days=REFRESH_DAYS - 1)).isoformat()
    todo = [d for d in days if d not in known or d >= recent]
    print(f"Days to fetch: {len(todo)} (of {DAILY_DAYS})")
    readiness = Readiness()
    try:
        for i, day in enumerate(todo, 1):
            known[day] = daily_row(api, day, readiness)
            print(f"  {day} ok ({i}/{len(todo)})")
    except RateLimited:
        rate_limited = True
        print("\nGarmin is rate limiting requests (429). Saving what we have; run again in 15-30 minutes.")
    daily = sorted((known[d] for d in days if d in known), key=lambda r: r["date"], reverse=True)
    save(out, "daily.json", daily, f"Daily values from the last {DAILY_DAYS} days")

    status = []
    if not rate_limited:
        try:
            status = [status_row(api, today.isoformat())]
        except RateLimited:
            print("Garmin rate limited the training status request.")
    if status:
        save(out, "status.json", status, "Today's training status and VO2max")

    report("activities.json", activities)
    report("daily.json", daily)
    report("status.json", status)
    stamp.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    print(f"\nDone. The files are in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
