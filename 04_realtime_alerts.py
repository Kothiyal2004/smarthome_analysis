"""
04_realtime_alerts.py  (fixed)
------------------------------
Smart Home — Phase 2 Live Alert System

Usage:
    python 04_realtime_alerts.py               normal run
    python 04_realtime_alerts.py --test        fire ALL patterns right now
    python 04_realtime_alerts.py --hour 19     simulate a specific hour
"""

import pandas as pd
import time
import sys
import os
from datetime import datetime, date

try:
    from plyer import notification as desktop_notify
    DESKTOP_NOTIFY = True
except ImportError:
    DESKTOP_NOTIFY = False
    print("[INFO] plyer not installed — alerts print to terminal only.")
    print("       Run:  pip install plyer   to enable desktop popups.\n")

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
FREQ_CSV  = os.path.join(BASE_DIR, "output", "pattern_frequency.csv")
LOG_FILE  = os.path.join(BASE_DIR, "output", "alerts.log")

TEST_MODE     = "--test" in sys.argv
HOUR_OVERRIDE = None
if "--hour" in sys.argv:
    idx = sys.argv.index("--hour")
    try:
        HOUR_OVERRIDE = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        print("Usage: python 04_realtime_alerts.py --hour 19")
        sys.exit(1)

# ── load pattern_frequency.csv ─────────────────────────────────────────
if not os.path.exists(FREQ_CSV):
    print(f"ERROR: {FREQ_CSV} not found.")
    print("Run 02_pattern_analysis.py first.")
    sys.exit(1)

freq = pd.read_csv(FREQ_CSV)

# ── auto-detect the hour column (handles "hour" or "hour_of_day") ──────
if "hour" in freq.columns and "hour_of_day" not in freq.columns:
    freq = freq.rename(columns={"hour": "hour_of_day"})
elif "hour_of_day" not in freq.columns:
    hour_col = [c for c in freq.columns if "hour" in c.lower()]
    if hour_col:
        freq = freq.rename(columns={hour_col[0]: "hour_of_day"})
    else:
        print(f"ERROR: Cannot find hour column. Columns: {list(freq.columns)}")
        sys.exit(1)

# ── auto-detect user/device/service column names ──────────────────────
col_map = {}
for col in freq.columns:
    lc = col.lower().replace(" ", "_")
    if lc == "user_name":    col_map[col] = "User Name"
    elif lc == "device_name": col_map[col] = "Device Name"
    elif lc == "service":    col_map[col] = "Service"
if col_map:
    freq = freq.rename(columns=col_map)

triggers = freq[freq["confidence"].isin(["HIGH", "MEDIUM"])].copy().reset_index(drop=True)

# ── notification messages ──────────────────────────────────────────────
def make_message(row):
    h   = int(row["hour_of_day"])
    apm = f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}"
    u   = row["User Name"]
    dev = row["Device Name"]
    svc = row["Service"]
    templates = {
        ("bedroom_ac",       "turn_on"):          f"It's {apm}. Turn on the bedroom AC, {u}?",
        ("bedroom_ac",       "turn_off"):          f"It's {apm}. Turn off the bedroom AC, {u}?",
        ("bedroom_ac",       "set_temperature"):   f"Set bedroom AC to your usual temp, {u}?",
        ("kitchen_light",    "turn_on"):           f"Good {'morning' if h < 12 else 'evening'} {u}! Kitchen light on?",
        ("kitchen_light",    "turn_off"):          f"Done in the kitchen, {u}? Light off?",
        ("front_door_lock",  "lock"):              f"Heading out, {u}? Lock the front door?",
        ("front_door_lock",  "unlock"):            f"Welcome home, {u}! Unlock the front door?",
        ("living_room_tv",   "turn_on"):           f"It's {apm} — TV time, {u}? Turn it on?",
        ("living_room_tv",   "turn_off"):          f"Calling it a night, {u}? Turn off the TV?",
        ("living_room_ac",   "turn_on"):           f"It's {apm}. Cool the living room, {u}?",
        ("living_room_ac",   "set_temperature"):   f"Set living room AC to your usual temp, {u}?",
        ("bathroom_light",   "turn_on"):           f"Good morning {u}! Bathroom light on?",
        ("bathroom_light",   "turn_off"):          f"Bedtime, {u}? Bathroom light off?",
        ("bedroom_light",    "turn_on"):           f"It's {apm}. Bedroom light on, {u}?",
        ("bedroom_light",    "turn_off"):          f"Morning {u}! Bedroom light off?",
        ("garage_door",      "open"):              f"Heading out, {u}? Open the garage?",
        ("garage_door",      "close"):             f"Welcome home, {u}! Close the garage?",
        ("smart_thermostat", "set_temperature"):   f"Set the thermostat to your usual temp, {u}?",
    }
    return templates.get((dev, svc),
        f"{apm}: {svc.replace('_',' ')} {dev.replace('_',' ')} for {u}?")

triggers["message"] = triggers.apply(make_message, axis=1)

# ── cooldown ────────────────────────────────────────────────────────────
fired_today = {}

def cooldown_key(row):
    return (row["User Name"], row["Device Name"], row["Service"], int(row["hour_of_day"]))

def already_fired(row):
    return fired_today.get(cooldown_key(row)) == date.today()

def mark_fired(row):
    fired_today[cooldown_key(row)] = date.today()

# ── logging ─────────────────────────────────────────────────────────────
os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

def log(message, level="INFO"):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── send one notification ───────────────────────────────────────────────
def send_alert(row):
    title   = f"Smart Home — {row['User Name']}"
    message = row["message"]
    if DESKTOP_NOTIFY:
        try:
            desktop_notify.notify(
                title=title, message=message,
                app_name="Smart Home Alerts", timeout=10,
            )
        except Exception as e:
            log(f"Desktop notify failed: {e}", level="WARN")
    log(f"ALERT  {title}  |  {message}")
    mark_fired(row)

# ── TEST MODE ────────────────────────────────────────────────────────────
if TEST_MODE:
    log(f"=== TEST MODE — firing all {len(triggers)} HIGH/MEDIUM patterns ===")
    for _, row in triggers.iterrows():
        send_alert(row)
        time.sleep(1.5)
    log("=== TEST MODE complete ===")
    print(f"\nLog saved → {LOG_FILE}")
    sys.exit(0)

# ── HOUR SIMULATE MODE ───────────────────────────────────────────────────
if HOUR_OVERRIDE is not None:
    log(f"=== HOUR SIMULATE — testing {HOUR_OVERRIDE:02d}:00 ===")
    due = triggers[triggers["hour_of_day"] == HOUR_OVERRIDE]
    if due.empty:
        log(f"No HIGH/MEDIUM patterns at hour {HOUR_OVERRIDE:02d}:00")
    for _, row in due.iterrows():
        send_alert(row)
        time.sleep(1.5)
    log("=== HOUR SIMULATE complete ===")
    print(f"\nLog saved → {LOG_FILE}")
    sys.exit(0)

# ── MAIN LOOP ────────────────────────────────────────────────────────────
log("=" * 55)
log("  Smart Home Alert System — STARTED")
log(f"  Patterns loaded   : {len(triggers)}")
log(f"  Log file          : {LOG_FILE}")
log(f"  Desktop notify    : {'ON' if DESKTOP_NOTIFY else 'OFF (install plyer)'}")
log("  Press Ctrl+C to stop")
log("=" * 55)

try:
    while True:
        hour = datetime.now().hour
        due  = triggers[triggers["hour_of_day"] == hour]
        for _, row in due.iterrows():
            if not already_fired(row):
                send_alert(row)
        time.sleep(60)

except KeyboardInterrupt:
    log("Alert system stopped by user (Ctrl+C).")
    print(f"\nLog saved → {LOG_FILE}")