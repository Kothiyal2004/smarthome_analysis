"""
07_session_builder.py
─────────────────────────────────────────────────────────────────────
Groups cleaned_logs.csv into user behaviour sessions.

WHAT IS A SESSION?
  A session is a continuous burst of device activity by one user
  where no gap between consecutive events exceeds SESSION_GAP minutes.

  Example:
    18:58  Alice  front_door_lock → unlock          ┐
    19:01  Alice  kitchen_light   → turn_on          │ one session
    19:03  Alice  bedroom_ac      → turn_on          │
    19:10  Alice  bedroom_ac      → set_temperature  ┘
    (gap > 30 min)
    21:45  Alice  bedroom_light   → turn_off         ← new session

WHY SESSIONS?
  Raw logs are just a flat list of events.
  Sessions give context: "what does this user do together?"
  That context is what Markov chains and sequence miners need.

OUTPUT FILES:
  output/sessions.json   ← full session data (used by script 08)
  output/sessions.csv    ← flat table for reading in VS Code
  output/session_summary.csv  ← one row per session for quick analysis

USAGE:
  python 07_session_builder.py
  python 07_session_builder.py --gap 20      (20-min gap threshold)
  python 07_session_builder.py --min 2       (min events per session)
  python 07_session_builder.py --show        (print all sessions)
─────────────────────────────────────────────────────────────────────
"""

import pandas as pd
import json
import os
import sys
from datetime import timedelta
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
CSV_PATH            = os.path.join(BASE_DIR, "output", "cleaned_logs.csv")
SESSION_GAP_MINUTES = 30   # gap that separates two sessions
MIN_EVENTS          = 2    # sessions with fewer events are discarded
SHOW_ALL            = "--show" in sys.argv

if "--gap" in sys.argv:
    idx = sys.argv.index("--gap")
    try:
        SESSION_GAP_MINUTES = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        print("Usage: --gap <minutes>   e.g. --gap 20")
        raise SystemExit(1)

if "--min" in sys.argv:
    idx = sys.argv.index("--min")
    try:
        MIN_EVENTS = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        pass

# ── Load & validate ───────────────────────────────────────────────────
if not os.path.exists(CSV_PATH):
    print(f"ERROR: {CSV_PATH} not found.")
    print("Run python 01_load_data.py first.")
    raise SystemExit(1)

raw = pd.read_csv(CSV_PATH)

# Find columns regardless of capitalisation or spacing
def find_col(df, *keywords):
    for col in df.columns:
        lc = col.strip().lower().replace(" ", "_")
        if all(k in lc for k in keywords):
            return col
    return None

ts_col  = find_col(raw, "timestamp")
usr_col = find_col(raw, "user", "name")
uid_col = find_col(raw, "user", "id")
dev_col = find_col(raw, "device", "name")
svc_col = next((c for c in raw.columns if c.strip().lower() == "service"), None)
loc_col = find_col(raw, "location")
dom_col = find_col(raw, "domain")
did_col = find_col(raw, "device", "id")

missing = [n for n, c in [("timestamp",ts_col),("user_name",usr_col),
                           ("device_name",dev_col),("service",svc_col)] if c is None]
if missing:
    print(f"ERROR: missing columns: {missing}")
    print(f"Found columns: {list(raw.columns)}")
    raise SystemExit(1)

# Parse timestamp as string → datetime (avoids the "assemble" pandas bug)
raw[ts_col] = pd.to_datetime(raw[ts_col].astype(str), errors="coerce")
raw = raw.dropna(subset=[ts_col])

# Sort by user then time
raw = raw.sort_values([usr_col, ts_col]).reset_index(drop=True)

# Build canonical action label:  device_name::service
raw["_action"] = (
    raw[dev_col].astype(str).str.lower().str.strip() + "::" +
    raw[svc_col].astype(str).str.lower().str.strip()
)

print(f"{'='*60}")
print(f"  07 SESSION BUILDER")
print(f"{'='*60}")
print(f"  Loaded          : {len(raw):,} events")
print(f"  Users           : {raw[usr_col].nunique()}  "
      f"({', '.join(sorted(raw[usr_col].unique()))})")
print(f"  Devices         : {raw[dev_col].nunique()}")
print(f"  Date range      : {raw[ts_col].min().date()} → {raw[ts_col].max().date()}")
print(f"  Session gap     : {SESSION_GAP_MINUTES} minutes")
print(f"  Min session size: {MIN_EVENTS} events")
print()

# ── Build sessions ────────────────────────────────────────────────────
sessions   = []
session_id = 0

for user_name, udf in raw.groupby(usr_col):
    udf = udf.sort_values(ts_col).reset_index(drop=True)

    # Buffer holds events of the current in-progress session
    buffer = []

    def flush_buffer(buf, sid, uname):
        """Turn buffer into a session dict and append to sessions."""
        if len(buf) < MIN_EVENTS:
            return sid
        first = buf[0]
        last  = buf[-1]
        duration_sec = (last["ts"] - first["ts"]).total_seconds()
        actions   = [b["action"] for b in buf]
        devices   = [b["device"] for b in buf]
        services  = [b["service"] for b in buf]

        # Label the session by its dominant hour
        hours  = [b["ts"].hour for b in buf]
        h_mode = Counter(hours).most_common(1)[0][0]

        # Human-readable time label
        if   6  <= h_mode <= 8:   time_label = "morning_routine"
        elif 9  <= h_mode <= 11:  time_label = "late_morning"
        elif 12 <= h_mode <= 13:  time_label = "lunch"
        elif 14 <= h_mode <= 16:  time_label = "afternoon"
        elif 17 <= h_mode <= 19:  time_label = "evening_return"
        elif 20 <= h_mode <= 22:  time_label = "night_routine"
        elif 23 <= h_mode or h_mode <= 5: time_label = "late_night"
        else:                     time_label = "other"

        # Detect common behaviour patterns in sequence
        action_str = " ".join(actions)
        if "front_door_lock::unlock" in action_str:
            behaviour = "arriving_home"
        elif "front_door_lock::lock" in action_str:
            behaviour = "leaving_home"
        elif time_label == "morning_routine":
            behaviour = "morning_routine"
        elif time_label in ("night_routine", "late_night"):
            behaviour = "night_routine"
        elif "bedroom_ac::turn_on" in action_str or "living_room_ac::turn_on" in action_str:
            behaviour = "comfort_control"
        else:
            behaviour = "general"

        sessions.append({
            # Identity
            "session_id"   : sid,
            "user_id"      : buf[0].get("uid", uname),
            "user_name"    : uname,

            # Timing
            "date"         : first["ts"].strftime("%Y-%m-%d"),
            "day_of_week"  : first["ts"].strftime("%A"),
            "is_weekend"   : first["ts"].weekday() >= 5,
            "start_time"   : first["ts"].strftime("%H:%M:%S"),
            "end_time"     : last["ts"].strftime("%H:%M:%S"),
            "hour_start"   : first["ts"].hour,
            "duration_sec" : int(duration_sec),

            # Content
            "n_events"     : len(buf),
            "sequence"     : actions,           # full ordered list of actions
            "devices"      : list(dict.fromkeys(devices)),  # unique, order-preserved
            "services_used": list(dict.fromkeys(services)),

            # Labels
            "time_label"   : time_label,
            "behaviour"    : behaviour,

            # Transition pairs — (A→B) for Markov chain
            "transitions"  : [
                {"from": actions[i], "to": actions[i+1]}
                for i in range(len(actions)-1)
            ],
        })
        return sid + 1

    for _, row in udf.iterrows():
        ts     = row[ts_col]
        action = row["_action"]
        device = str(row[dev_col]).lower().strip()
        service= str(row[svc_col]).lower().strip()
        uid    = str(row[uid_col]) if uid_col else user_name
        loc    = str(row[loc_col]) if loc_col else ""

        if buffer:
            gap_minutes = (ts - buffer[-1]["ts"]).total_seconds() / 60
            if gap_minutes > SESSION_GAP_MINUTES:
                session_id = flush_buffer(buffer, session_id, user_name)
                buffer = []

        buffer.append({
            "ts"     : ts,
            "action" : action,
            "device" : device,
            "service": service,
            "uid"    : uid,
            "loc"    : loc,
        })

    # Flush last buffer
    session_id = flush_buffer(buffer, session_id, user_name)

# ── Save sessions.json ────────────────────────────────────────────────
os.makedirs(os.path.join(BASE_DIR, "output"), exist_ok=True)

# Make JSON serialisable (booleans, ints etc.)
def make_serialisable(obj):
    if isinstance(obj, bool):
        return bool(obj)
    if hasattr(obj, "item"):   # numpy scalar
        return obj.item()
    return obj

json_path = os.path.join(BASE_DIR, "output", "sessions.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(sessions, f, indent=2, default=make_serialisable)

# ── Save sessions.csv (flat — one row per event per session) ──────────
flat_rows = []
for s in sessions:
    for step_idx, action in enumerate(s["sequence"]):
        dev, svc = action.split("::", 1) if "::" in action else (action, "")
        flat_rows.append({
            "session_id"  : s["session_id"],
            "user_id"     : s["user_id"],
            "user_name"   : s["user_name"],
            "date"        : s["date"],
            "day_of_week" : s["day_of_week"],
            "is_weekend"  : s["is_weekend"],
            "hour_start"  : s["hour_start"],
            "time_label"  : s["time_label"],
            "behaviour"   : s["behaviour"],
            "step"        : step_idx + 1,
            "action"      : action,
            "device_name" : dev,
            "service"     : svc,
            "n_in_session": s["n_events"],
            "duration_sec": s["duration_sec"],
        })
csv_path = os.path.join(BASE_DIR, "output", "sessions.csv")
pd.DataFrame(flat_rows).to_csv(csv_path, index=False)

# ── Save session_summary.csv (one row per session) ────────────────────
summary_rows = []
for s in sessions:
    summary_rows.append({
        "session_id"  : s["session_id"],
        "user_name"   : s["user_name"],
        "date"        : s["date"],
        "day_of_week" : s["day_of_week"],
        "is_weekend"  : s["is_weekend"],
        "start_time"  : s["start_time"],
        "end_time"    : s["end_time"],
        "hour_start"  : s["hour_start"],
        "n_events"    : s["n_events"],
        "duration_sec": s["duration_sec"],
        "time_label"  : s["time_label"],
        "behaviour"   : s["behaviour"],
        "sequence"    : " → ".join(s["sequence"]),
        "devices"     : ", ".join(s["devices"]),
    })
summary_path = os.path.join(BASE_DIR, "output", "session_summary.csv")
pd.DataFrame(summary_rows).to_csv(summary_path, index=False)

# ── Print results ─────────────────────────────────────────────────────
print(f"{'='*60}")
print(f"  SESSIONS FOUND: {len(sessions)}")
print(f"{'='*60}")
print()

for user in sorted({s["user_name"] for s in sessions}):
    u = [s for s in sessions if s["user_name"] == user]
    lengths     = [s["n_events"] for s in u]
    durations   = [s["duration_sec"] for s in u]
    behaviours  = Counter(s["behaviour"] for s in u)
    time_labels = Counter(s["time_label"] for s in u)

    print(f"  ── {user} ──────────────────────────────────")
    print(f"  Sessions total    : {len(u)}")
    print(f"  Avg events/session: {sum(lengths)/len(lengths):.1f}")
    print(f"  Avg duration      : {sum(durations)/len(durations)/60:.1f} min")
    print(f"  Behaviour types   : {dict(behaviours.most_common())}")
    print(f"  Peak time labels  : {dict(time_labels.most_common(3))}")
    print()

    # Show 3 richest example sessions
    top = sorted(u, key=lambda x: -x["n_events"])[:3]
    print(f"  Top {len(top)} sessions by length:")
    for s in top:
        seq_display = " → ".join(s["sequence"])
        if len(seq_display) > 70:
            seq_display = " → ".join(s["sequence"][:4]) + f"  … (+{len(s['sequence'])-4})"
        print(f"    [{s['date']} {s['start_time']}]  "
              f"{s['n_events']} events  [{s['behaviour']}]")
        print(f"      {seq_display}")
    print()

    # Behaviour summary
    print(f"  Behaviour breakdown:")
    for beh, cnt in behaviours.most_common():
        pct = cnt / len(u) * 100
        bar = "█" * int(pct / 5)
        print(f"    {beh:<22} {cnt:>3} sessions  {pct:5.1f}%  {bar}")
    print()

# ── Transition pairs summary (what follows what across all users) ─────
all_transitions = []
for s in sessions:
    for t in s["transitions"]:
        all_transitions.append({
            "user"   : s["user_name"],
            "from"   : t["from"],
            "to"     : t["to"],
            "hour"   : s["hour_start"],
            "behaviour": s["behaviour"],
        })

trans_df = pd.DataFrame(all_transitions)
print(f"{'='*60}")
print(f"  TOP TRANSITIONS (what users do NEXT after each action)")
print(f"{'='*60}")

for user in sorted(trans_df["user"].unique()):
    utr = trans_df[trans_df["user"] == user]
    counts = utr.groupby(["from","to"]).size().reset_index(name="count")
    total_per_from = utr.groupby("from").size().reset_index(name="total")
    counts = counts.merge(total_per_from, on="from")
    counts["probability"] = (counts["count"] / counts["total"] * 100).round(1)
    top = counts.sort_values("probability", ascending=False).head(8)

    print(f"\n  {user}")
    print(f"  {'After this action':<38}  {'User next does':<32}  Prob")
    print(f"  {'─'*38}  {'─'*32}  {'─'*6}")
    for _, r in top.iterrows():
        stars = "★★★" if r.probability >= 70 else ("★★ " if r.probability >= 50 else "★  ")
        print(f"  {r['from']:<38}  {r['to']:<32}  "
              f"{r.probability:5.1f}%  {stars}")

print()
print(f"{'='*60}")
print(f"  OUTPUT FILES")
print(f"{'='*60}")
print(f"  sessions.json        → {json_path}")
print(f"    {len(sessions)} sessions, full sequence + transitions")
print(f"  sessions.csv         → {csv_path}")
print(f"    {len(flat_rows)} rows — one per event per session")
print(f"  session_summary.csv  → {summary_path}")
print(f"    {len(summary_rows)} rows — one per session")
print()
print(f"  Next step:")
print(f"    python 08_markov_builder.py")