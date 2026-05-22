"""
06_import_homeassistant.py  (fixed)
------------------------------------
Exports real device events from Home Assistant into cleaned_logs.csv.

After running:
    python 02_pattern_analysis.py
    python 03_notifications.py
    pkill -f 04_realtime_alerts.py
    nohup python 04_realtime_alerts.py >> output/alerts.log 2>&1 &

Usage:
    python 06_import_homeassistant.py
    python 06_import_homeassistant.py --days 60
"""

import sqlite3
import pandas as pd
import os
import sys
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Find HA database automatically ───────────────────────────────────
SEARCH_PATHS = [
    os.path.expanduser("~/.homeassistant/home-assistant_v2.db"),
    "/config/home-assistant_v2.db",
    os.path.expanduser("~/homeassistant/home-assistant_v2.db"),
    os.path.expanduser("~/config/home-assistant_v2.db"),
    "/homeassistant/home-assistant_v2.db",
    "/usr/share/hassio/homeassistant/home-assistant_v2.db",
]

# Also glob-search common locations
SEARCH_PATHS += glob.glob(
    os.path.expanduser("~/**/home-assistant_v2.db"), recursive=True
)

HA_DB_PATH = None
for p in SEARCH_PATHS:
    if os.path.exists(p):
        HA_DB_PATH = p
        break

if HA_DB_PATH is None:
    print("=" * 60)
    print("  Home Assistant database not found automatically.")
    print("=" * 60)
    print()
    print("  Searched these locations:")
    for p in SEARCH_PATHS[:6]:
        print(f"    {p}")
    print()
    print("  To find it manually, run in terminal:")
    print("    find / -name 'home-assistant_v2.db' 2>/dev/null")
    print()
    print("  Then open 06_import_homeassistant.py in VS Code")
    print("  and set HA_DB_PATH at the top of the file to the")
    print("  path shown above.")
    print()
    print("  Example:")
    print("    HA_DB_PATH = '/your/actual/path/home-assistant_v2.db'")
    sys.exit(1)

print(f"  Found database: {HA_DB_PATH}")

DAYS = 30
if "--days" in sys.argv:
    idx = sys.argv.index("--days")
    try:
        DAYS = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        pass

print(f"  Exporting last {DAYS} days...")
print()

# ── Connect and query ─────────────────────────────────────────────────
conn = sqlite3.connect(HA_DB_PATH)

# Try new schema (HA 2023+) first, fall back to old schema
try:
    df = pd.read_sql(f"""
        SELECT
            datetime(s.last_updated_ts, 'unixepoch', 'localtime') AS timestamp,
            sm.entity_id                                            AS device_id,
            s.state                                                 AS service,
            s.attributes                                            AS service_data
        FROM states s
        JOIN states_meta sm ON s.metadata_id = sm.metadata_id
        WHERE s.last_updated_ts > unixepoch('now', '-{DAYS} days')
          AND s.state NOT IN ('unavailable', 'unknown', '')
        ORDER BY s.last_updated_ts
    """, conn)
    schema = "new (2023+)"
except Exception:
    # Old schema
    df = pd.read_sql(f"""
        SELECT
            datetime(last_updated) AS timestamp,
            entity_id              AS device_id,
            state                  AS service,
            attributes             AS service_data
        FROM states
        WHERE last_updated > datetime('now', '-{DAYS} days')
          AND state NOT IN ('unavailable', 'unknown', '')
        ORDER BY last_updated
    """, conn)
    schema = "legacy"

conn.close()
print(f"  Schema detected: {schema}")

if df.empty:
    print("  No events found in the last", DAYS, "days.")
    print("  Try --days 90 for a longer range.")
    sys.exit(0)

# ── Enrich ────────────────────────────────────────────────────────────
df["timestamp"]   = pd.to_datetime(df["timestamp"])
df["domain"]      = df["device_id"].str.split(".").str[0]
df["device_name"] = df["device_id"].str.split(".").str[1]
df["user_name"]   = "Home"
df["user_id"]     = "USR-001"
df["event"]       = "state_changed"
df["level"]       = "INFO"
df["location"]    = ""
df["is_weekend"]  = df["timestamp"].dt.weekday >= 5
df["hour_of_day"] = df["timestamp"].dt.hour
df["day_of_week"] = df["timestamp"].dt.day_name()
df["date"]        = df["timestamp"].dt.date

# ── Save ──────────────────────────────────────────────────────────────
out = os.path.join(BASE_DIR, "output", "cleaned_logs.csv")
df.to_csv(out, index=False)

print()
print("=" * 56)
print("  HOME ASSISTANT EXPORT COMPLETE")
print("=" * 56)
print(f"  Rows exported  : {len(df)}")
print(f"  Date range     : {df['date'].min()} -> {df['date'].max()}")
print(f"  Unique devices : {df['device_id'].nunique()}")
print(f"  Domains found  : {', '.join(sorted(df['domain'].unique()[:8]))}")
print(f"  Saved to       : {out}")
print()
print("  Next steps:")
print("    python 02_pattern_analysis.py")
print("    python 03_notifications.py")
print("    pkill -f 04_realtime_alerts.py")
print("    nohup python 04_realtime_alerts.py >> output/alerts.log 2>&1 &")