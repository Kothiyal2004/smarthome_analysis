"""
09_behaviour_engine.py
───────────────────────
The live prediction engine.

Watches cleaned_logs.csv for new events (polls every 30 seconds).
When a new event arrives:
  1. Identify the user
  2. Look up Markov table: what does this user do NEXT after this action?
  3. Check time context: does the time match a known pattern?
  4. If confidence >= threshold → fire a suggestion

ALSO checks time-based patterns from pattern_frequency.csv
so BOTH triggers work: action-sequence AND time-of-day.

Usage:
    python 09_behaviour_engine.py
    python 09_behaviour_engine.py --test   (simulate a trigger event)
    python 09_behaviour_engine.py --threshold 0.6  (min confidence)
"""

import json, os, sys, time
import pandas as pd
from datetime import datetime, date, timedelta

# ── Config ────────────────────────────────────────────────────────────
BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
LOG_CSV         = os.path.join(BASE_DIR, "output", "cleaned_logs.csv")
MARKOV_JSON     = os.path.join(BASE_DIR, "output", "markov_table.json")
FREQ_CSV        = os.path.join(BASE_DIR, "output", "pattern_frequency.csv")
ALERTS_LOG      = os.path.join(BASE_DIR, "output", "behaviour_alerts.log")

THRESHOLD       = 0.60   # minimum probability to fire a suggestion
POLL_SECONDS    = 30     # how often to check for new events
COOLDOWN_MINS   = 60     # don't repeat same suggestion within this window
TEST_MODE       = "--test" in sys.argv

if "--threshold" in sys.argv:
    idx = sys.argv.index("--threshold")
    try:
        THRESHOLD = float(sys.argv[idx + 1])
    except (IndexError, ValueError):
        pass

# ── Load Markov table ─────────────────────────────────────────────────
if not os.path.exists(MARKOV_JSON):
    print("ERROR: markov_table.json not found.")
    print("Run:  python 07_session_builder.py")
    print("Then: python 08_markov_builder.py")
    raise SystemExit(1)

with open(MARKOV_JSON) as f:
    markov = json.load(f)

# ── Load time-based patterns ──────────────────────────────────────────
time_patterns = pd.DataFrame()
if os.path.exists(FREQ_CSV):
    time_patterns = pd.read_csv(FREQ_CSV)
    time_patterns.columns = [c.strip().lower().replace(" ","_") for c in time_patterns.columns]
    if "hour" in time_patterns.columns and "hour_of_day" not in time_patterns.columns:
        time_patterns = time_patterns.rename(columns={"hour": "hour_of_day"})
    time_patterns = time_patterns[time_patterns["confidence"].isin(["HIGH","MEDIUM"])]

# ── Cooldown tracker ──────────────────────────────────────────────────
# key: (user, suggestion_about) → last fired datetime
fired_recently = {}

def on_cooldown(user, about):
    key = (user, about)
    last = fired_recently.get(key)
    if last and (datetime.now() - last).total_seconds() < COOLDOWN_MINS * 60:
        return True
    return False

def mark_fired(user, about):
    fired_recently[(user, about)] = datetime.now()

# ── Notification / logging ────────────────────────────────────────────
try:
    from plyer import notification as desktop_notify
    DESKTOP = True
except ImportError:
    DESKTOP = False

def send_suggestion(user, trigger, predicted, confidence, reason):
    """Build and deliver a suggestion."""
    dev  = predicted.split("::")[0].replace("_", " ")
    svc  = predicted.split("::")[-1].replace("_", " ")
    hour = datetime.now().hour
    apm  = f"{hour%12 or 12}:00 {'AM' if hour<12 else 'PM'}"

    # Build natural message
    templates = {
        "bedroom_ac::turn_on"         : f"It's {apm}. Shall I turn on the bedroom AC, {user}?",
        "bedroom_ac::turn_off"        : f"Want me to turn off the bedroom AC, {user}?",
        "kitchen_light::turn_on"      : f"Want the kitchen light on, {user}?",
        "kitchen_light::turn_off"     : f"Done in the kitchen, {user}? Light off?",
        "front_door_lock::lock"       : f"Heading out, {user}? Want me to lock the door?",
        "front_door_lock::unlock"     : f"Welcome home, {user}! Shall I unlock the door?",
        "living_room_tv::turn_on"     : f"It's {apm} — TV time, {user}? Turn it on?",
        "living_room_ac::turn_on"     : f"Shall I cool the living room, {user}?",
        "bathroom_light::turn_on"     : f"Good morning {user}! Bathroom light on?",
        "garage_door::open"           : f"Heading out, {user}? Open the garage?",
        "garage_door::close"          : f"Home now, {user}? Shall I close the garage?",
        "bedroom_light::turn_on"      : f"Bedroom light on, {user}?",
        "smart_thermostat::set_temperature": f"Set thermostat to your usual temp, {user}?",
    }
    msg = templates.get(predicted,
        f"Based on your history — shall I {svc} the {dev}, {user}?")

    title = f"Smart Home — {user}"
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Desktop popup
    if DESKTOP:
        try:
            desktop_notify.notify(title=title, message=msg,
                                  app_name="Smart Home", timeout=10)
        except Exception:
            pass

    # Log
    line = (f"[{ts}] SUGGESTION  {user}  |  "
            f"trigger={trigger}  predicted={predicted}  "
            f"confidence={confidence:.0%}  reason={reason}  |  {msg}")
    print(line)
    with open(ALERTS_LOG, "a") as f:
        f.write(line + "\n")

    mark_fired(user, predicted)

# ── Core prediction logic ─────────────────────────────────────────────
def predict_from_action(user, action):
    """Look up Markov table. Return list of (predicted_action, probability)."""
    user_table = markov.get(user, {})
    nexts = user_table.get(action, [])
    return [(n["next_action"], n["probability"]) for n in nexts
            if n["probability"] >= THRESHOLD]

def predict_from_time(user, hour):
    """Look up time-based patterns for this user+hour."""
    if time_patterns.empty:
        return []
    col = next((c for c in time_patterns.columns if "user" in c and "name" in c), None)
    if not col:
        return []
    matches = time_patterns[
        (time_patterns[col].str.lower() == user.lower()) &
        (time_patterns["hour_of_day"] == hour)
    ]
    results = []
    for _, r in matches.iterrows():
        dev = str(r.get("device_name","")).lower().strip()
        svc = str(r.get("service","")).lower().strip()
        pct = float(r.get("pct", 0)) / 100
        if dev and svc and pct >= THRESHOLD:
            results.append((f"{dev}::{svc}", pct))
    return results

def process_event(user, action, hour):
    """Process one incoming event — fire suggestions if patterns match."""
    fired = False

    # Trigger 1: sequence-based prediction
    seq_predictions = predict_from_action(user, action)
    for predicted, prob in seq_predictions:
        if not on_cooldown(user, predicted):
            send_suggestion(user, action, predicted, prob, "sequence")
            fired = True

    # Trigger 2: time-based prediction
    time_predictions = predict_from_time(user, hour)
    for predicted, prob in time_predictions:
        if not on_cooldown(user, predicted):
            send_suggestion(user, action, predicted, prob, "time_pattern")
            fired = True

    if not fired:
        print(f"  [{datetime.now().strftime('%H:%M:%S')}]  "
              f"{user} | {action} | no prediction above {THRESHOLD:.0%}")

# ── Test mode: simulate events ────────────────────────────────────────
if TEST_MODE:
    print("=" * 56)
    print("  TEST MODE — simulating trigger events")
    print("=" * 56)
    test_events = [
        ("Alice", "front_door_lock::unlock", 18),
        ("Alice", "bathroom_light::turn_on", 6),
        ("Bob",   "living_room_tv::turn_on", 20),
        ("Carol", "kitchen_light::turn_off", 20),
        ("Carol", "front_door_lock::lock",   9),
    ]
    for user, action, hour in test_events:
        print(f"\n  Simulating: {user} → {action} at hour {hour}")
        process_event(user, action, hour)
        time.sleep(1)
    print("\n  Test complete. Check behaviour_alerts.log")
    raise SystemExit(0)

# ── Main loop: watch for new log events ───────────────────────────────
print("=" * 56)
print("  BEHAVIOUR ENGINE — STARTED")
print("=" * 56)
print(f"  Watching: {LOG_CSV}")
print(f"  Threshold: {THRESHOLD:.0%} confidence")
print(f"  Poll interval: {POLL_SECONDS}s")
print(f"  Desktop notify: {'ON' if DESKTOP else 'OFF'}")
print("  Press Ctrl+C to stop\n")

last_seen_count = 0

try:
    while True:
        if os.path.exists(LOG_CSV):
            df = pd.read_csv(LOG_CSV)
            df.columns = [c.strip().lower().replace(" ","_") for c in df.columns]

            ts_col  = next((c for c in df.columns if "timestamp" in c), None)
            usr_col = next((c for c in df.columns if "user" in c and "name" in c), None)
            dev_col = next((c for c in df.columns if "device" in c and "name" in c), None)
            svc_col = next((c for c in df.columns if c == "service"), None)

            if all([ts_col, usr_col, dev_col, svc_col]):
                df[ts_col] = pd.to_datetime(df[ts_col].astype(str), errors="coerce")
                df = df.dropna(subset=[ts_col]).sort_values(ts_col)
                df["action"] = (df[dev_col].str.lower().str.strip() + "::" +
                                df[svc_col].str.lower().str.strip())

                current_count = len(df)
                if current_count > last_seen_count:
                    # New events arrived
                    new_events = df.iloc[last_seen_count:]
                    for _, row in new_events.iterrows():
                        user   = str(row[usr_col])
                        action = str(row["action"])
                        hour   = int(row[ts_col].hour) if hasattr(row[ts_col], "hour") else datetime.now().hour
                        process_event(user, action, hour)
                    last_seen_count = current_count

        time.sleep(POLL_SECONDS)

except KeyboardInterrupt:
    print("\n  Behaviour engine stopped.")
    print(f"  Log saved → {ALERTS_LOG}")