"""
11_unified_engine.py
────────────────────────────────────────────────────────────────
The UNIFIED smart home engine.
Combines BOTH engines into one:

  Engine A — Time-based  (from 04_realtime_alerts.py)
    Checks clock every 60s → fires when hour matches a pattern

  Engine B — Sequence-based  (from 09_behaviour_engine.py)
    Watches log for new events → predicts next action via Markov

Both run together in one loop. Whichever fires first wins.
Cooldown prevents duplicate suggestions.

Usage:
    python 11_unified_engine.py              normal — runs forever
    python 11_unified_engine.py --test       fires all triggers now
    python 11_unified_engine.py --hour 19    simulate one hour

Output:
    output/unified_alerts.log
────────────────────────────────────────────────────────────────
"""

import pandas as pd
import json
import os
import sys
import time
from datetime import datetime, date

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
OUT          = os.path.join(BASE_DIR, "output")
FREQ_CSV     = os.path.join(OUT, "pattern_frequency.csv")
MARKOV_JSON  = os.path.join(OUT, "markov_table.json")
LOG_CSV      = os.path.join(OUT, "cleaned_logs.csv")
ALERT_LOG    = os.path.join(OUT, "unified_alerts.log")

CONFIDENCE   = 0.60   # minimum probability to fire
POLL_SECS    = 30     # check for new log events every 30s
COOLDOWN_MIN = 60     # don't repeat same suggestion within 60 min

TEST_MODE    = "--test"  in sys.argv
HOUR_OVERRIDE = None
if "--hour" in sys.argv:
    idx = sys.argv.index("--hour")
    try:
        HOUR_OVERRIDE = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        pass

# ── Desktop notifications ─────────────────────────────────────────────
try:
    from plyer import notification as _notify
    DESKTOP = True
except ImportError:
    DESKTOP = False

# ── Load data ─────────────────────────────────────────────────────────
def require(path, name, hint):
    if not os.path.exists(path):
        print(f"ERROR: {name} not found.")
        print(f"Run: {hint}")
        raise SystemExit(1)

require(FREQ_CSV,    "pattern_frequency.csv", "python 02_pattern_analysis.py")
require(MARKOV_JSON, "markov_table.json",     "python 08_markov_builder.py")
require(LOG_CSV,     "cleaned_logs.csv",      "python 01_load_data.py")

# Time-based patterns
freq = pd.read_csv(FREQ_CSV)
freq.columns = [c.strip().lower().replace(" ","_") for c in freq.columns]
if "hour" in freq.columns and "hour_of_day" not in freq.columns:
    freq = freq.rename(columns={"hour": "hour_of_day"})
usr_col = next(c for c in freq.columns if "user" in c and "name" in c)
dev_col = next(c for c in freq.columns if "device" in c and "name" in c)
time_triggers = freq[freq["confidence"].isin(["HIGH","MEDIUM"])].copy()

# Sequence-based patterns
with open(MARKOV_JSON) as f:
    markov = json.load(f)

print(f"  Time patterns loaded  : {len(time_triggers)}")
print(f"  Markov users loaded   : {list(markov.keys())}")

# ── Message builder ───────────────────────────────────────────────────
def make_msg(user, device, service, source="time"):
    h   = datetime.now().hour
    apm = f"{h%12 or 12}:00 {'AM' if h<12 else 'PM'}"
    dev = device.replace("_"," ")
    svc = service.replace("_"," ")
    T = {
        ("bedroom_ac",        "turn_on"):          f"It's {apm}. Shall I turn on the bedroom AC, {user}?",
        ("bedroom_ac",        "turn_off"):          f"Want me to turn off the bedroom AC, {user}?",
        ("bedroom_ac",        "set_temperature"):   f"Set bedroom AC to your usual temp, {user}?",
        ("kitchen_light",     "turn_on"):           f"Good {'morning' if h<12 else 'evening'} {user}! Kitchen light on?",
        ("kitchen_light",     "turn_off"):          f"Done in the kitchen, {user}? Light off?",
        ("front_door_lock",   "lock"):              f"Heading out, {user}? Want me to lock the door?",
        ("front_door_lock",   "unlock"):            f"Welcome home, {user}! Shall I unlock the door?",
        ("living_room_tv",    "turn_on"):           f"It's {apm} — TV time, {user}? Turn it on?",
        ("living_room_tv",    "turn_off"):          f"Calling it a night, {user}? Turn off the TV?",
        ("living_room_ac",    "turn_on"):           f"It's {apm}. Cool the living room, {user}?",
        ("bathroom_light",    "turn_on"):           f"Good morning {user}! Bathroom light on?",
        ("bathroom_light",    "turn_off"):          f"Bedtime, {user}? Bathroom light off?",
        ("bedroom_light",     "turn_on"):           f"It's {apm}. Bedroom light on, {user}?",
        ("bedroom_light",     "turn_off"):          f"Morning {user}! Bedroom light off?",
        ("garage_door",       "open"):              f"Heading out, {user}? Open the garage?",
        ("garage_door",       "close"):             f"Home now, {user}! Close the garage?",
        ("smart_thermostat",  "set_temperature"):   f"Set thermostat to your usual temp, {user}?",
    }
    return T.get((device, service),
        f"Based on your habits — shall I {svc} the {dev}, {user}?")

# ── Cooldown ──────────────────────────────────────────────────────────
_fired = {}  # key → last fired datetime

def on_cooldown(key):
    last = _fired.get(key)
    if last and (datetime.now() - last).total_seconds() < COOLDOWN_MIN * 60:
        return True
    return False

def mark(key):
    _fired[key] = datetime.now()

# ── Send one notification ─────────────────────────────────────────────
os.makedirs(OUT, exist_ok=True)

def send(user, device, service, confidence, source):
    key = (user, device, service)
    if on_cooldown(key):
        return
    msg   = make_msg(user, device, service, source)
    title = f"Smart Home — {user}"
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    src_tag = "TIME" if source == "time" else "SEQUENCE"
    line  = (f"[{ts}] [{src_tag}]  {user}  |  "
             f"{device}::{service}  conf={confidence:.0%}  |  {msg}")
    print(line)
    with open(ALERT_LOG, "a") as f:
        f.write(line + "\n")
    if DESKTOP:
        try:
            _notify.notify(title=title, message=msg,
                           app_name="Smart Home", timeout=10)
        except Exception:
            pass
    mark(key)

# ── Engine A: Time-based ──────────────────────────────────────────────
def check_time_patterns(hour):
    due = time_triggers[time_triggers["hour_of_day"] == hour]
    for _, row in due.iterrows():
        user   = str(row[usr_col])
        device = str(row[dev_col])
        svc    = str(row["service"])
        pct    = float(row.get("pct", 0)) / 100
        if pct >= CONFIDENCE:
            send(user, device, svc, pct, "time")

# ── Engine B: Sequence-based ──────────────────────────────────────────
_last_log_count = 0

def check_new_events():
    global _last_log_count
    if not os.path.exists(LOG_CSV):
        return
    df = pd.read_csv(LOG_CSV)
    df.columns = [c.strip().lower().replace(" ","_") for c in df.columns]
    ts_col  = next((c for c in df.columns if "timestamp" in c), None)
    usr_col2 = next((c for c in df.columns if "user" in c and "name" in c), None)
    dev_col2 = next((c for c in df.columns if "device" in c and "name" in c), None)
    svc_col  = next((c for c in df.columns if c == "service"), None)
    if not all([ts_col, usr_col2, dev_col2, svc_col]):
        return
    current = len(df)
    if current <= _last_log_count:
        return
    new_rows = df.iloc[_last_log_count:]
    _last_log_count = current
    for _, row in new_rows.iterrows():
        user   = str(row[usr_col2])
        device = str(row[dev_col2]).lower().strip()
        svc    = str(row[svc_col]).lower().strip()
        action = f"{device}::{svc}"
        hour   = datetime.now().hour
        # Look up Markov table
        user_table = markov.get(user, {})
        nexts = user_table.get(action, [])
        for n in nexts:
            if n["probability"] >= CONFIDENCE:
                pred_dev = n["next_action"].split("::")[0] if "::" in n["next_action"] else n["next_action"]
                pred_svc = n["next_action"].split("::")[-1] if "::" in n["next_action"] else ""
                send(user, pred_dev, pred_svc, n["probability"], "sequence")

# ── TEST MODE ─────────────────────────────────────────────────────────
if TEST_MODE:
    print("=" * 58)
    print("  TEST MODE — firing both engines now")
    print("=" * 58)
    print("\n  [ENGINE A — TIME-BASED] simulating current hour patterns")
    check_time_patterns(datetime.now().hour)
    print("\n  [ENGINE B — SEQUENCE] simulating trigger events")
    test_events = [
        ("Alice", "front_door_lock", "unlock"),
        ("Carol", "front_door_lock", "lock"),
        ("Carol", "kitchen_light",   "turn_off"),
        ("Bob",   "living_room_tv",  "turn_off"),
    ]
    for user, dev, svc in test_events:
        action = f"{dev}::{svc}"
        print(f"\n  Trigger: {user} → {action}")
        user_table = markov.get(user, {})
        for n in user_table.get(action, []):
            if n["probability"] >= CONFIDENCE:
                pred_dev = n["next_action"].split("::")[0]
                pred_svc = n["next_action"].split("::")[-1] if "::" in n["next_action"] else ""
                send(user, pred_dev, pred_svc, n["probability"], "sequence")
        time.sleep(1)
    print(f"\n  Log saved → {ALERT_LOG}")
    raise SystemExit(0)

# ── HOUR SIMULATE ─────────────────────────────────────────────────────
if HOUR_OVERRIDE is not None:
    print(f"Simulating hour {HOUR_OVERRIDE:02d}:00")
    check_time_patterns(HOUR_OVERRIDE)
    raise SystemExit(0)

# ── MAIN LOOP ─────────────────────────────────────────────────────────
print("=" * 58)
print("  UNIFIED SMART HOME ENGINE — STARTED")
print("=" * 58)
print(f"  Time patterns   : {len(time_triggers)}")
print(f"  Markov users    : {list(markov.keys())}")
print(f"  Confidence      : {CONFIDENCE:.0%}")
print(f"  Poll interval   : {POLL_SECS}s")
print(f"  Desktop notify  : {'ON' if DESKTOP else 'OFF'}")
print(f"  Log file        : {ALERT_LOG}")
print("  Press Ctrl+C to stop\n")

try:
    while True:
        now  = datetime.now()
        hour = now.hour
        # Engine A — time
        check_time_patterns(hour)
        # Engine B — sequence
        check_new_events()
        time.sleep(POLL_SECS)
except KeyboardInterrupt:
    print(f"\n  Engine stopped. Log saved → {ALERT_LOG}")