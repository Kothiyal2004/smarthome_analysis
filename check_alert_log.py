"""
check_alerts_log.py
-------------------
Reads output/alerts.log and prints a clean summary.

Usage:
    python check_alerts_log.py          (today only)
    python check_alerts_log.py --all    (full history)
"""

import os
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "output", "alerts.log")
SHOW_ALL = "--all" in sys.argv

if not os.path.exists(LOG_FILE):
    print("No alerts.log found yet.")
    print("Run:  python 04_realtime_alerts.py --test")
    sys.exit(0)

with open(LOG_FILE, encoding="utf-8") as f:
    lines = f.readlines()

today_str    = str(date.today())
all_alerts   = [l.strip() for l in lines if "ALERT" in l]
today_alerts = [l for l in all_alerts if l.startswith(f"[{today_str}")]
warnings     = [l.strip() for l in lines if "[WARN]" in l]

target = all_alerts if SHOW_ALL else today_alerts
label  = "ALL TIME" if SHOW_ALL else f"TODAY ({today_str})"

print("=" * 62)
print(f"  SMART HOME ALERT LOG — {label}")
print("=" * 62)

if not target:
    print(f"\n  No alerts fired {'in history' if SHOW_ALL else 'today'} yet.")
    print("  Run:  python 04_realtime_alerts.py --test")
else:
    print(f"\n  Total alerts : {len(target)}\n")

    users = {}
    for line in target:
        if "Smart Home —" in line:
            user = line.split("Smart Home —")[1].split("|")[0].strip()
            users[user] = users.get(user, 0) + 1

    print("  By user:")
    for u, c in sorted(users.items()):
        print(f"    {u:<12}  {c} alert{'s' if c != 1 else ''}")

    print(f"\n  {'─' * 58}")
    for line in target:
        if "] [INFO] " in line:
            ts  = line[1:20]
            msg = line.split("] [INFO] ")[-1]
            print(f"  {ts}  {msg}")
        else:
            print(f"  {line}")

if warnings:
    print(f"\n  Warnings:")
    for w in warnings[-5:]:
        print(f"    {w}")

print(f"\n  Log file: {LOG_FILE}")
print("=" * 62)