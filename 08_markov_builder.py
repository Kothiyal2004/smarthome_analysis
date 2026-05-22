"""
08_markov_builder.py
────────────────────
Builds a Markov transition table from session sequences.

For each user, for each action A in their sessions:
  P(B | A) = how often B immediately follows A / total times A appears

Output:
  output/markov_table.json   ← transition probabilities per user
  output/markov_table.csv    ← flat table for inspection

Usage:
    python 08_markov_builder.py
    python 08_markov_builder.py --min-support 3   (need 3+ occurrences)
"""

import json, os, sys
import pandas as pd
from collections import defaultdict

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
JSON_PATH   = os.path.join(BASE_DIR, "output", "sessions.json")
MIN_SUPPORT = 3   # minimum times a transition must appear

if "--min-support" in sys.argv:
    idx = sys.argv.index("--min-support")
    try:
        MIN_SUPPORT = int(sys.argv[idx + 1])
    except (IndexError, ValueError):
        pass

if not os.path.exists(JSON_PATH):
    print("ERROR: sessions.json not found. Run 07_session_builder.py first.")
    raise SystemExit(1)

with open(JSON_PATH) as f:
    sessions = json.load(f)

print(f"Loaded {len(sessions)} sessions")
print(f"Min support threshold: {MIN_SUPPORT}\n")

# ── Build transition counts ───────────────────────────────────────────
# Structure: {user: {action_A: {action_B: count}}}
transition_counts = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
action_counts     = defaultdict(lambda: defaultdict(int))

for session in sessions:
    user = session["user_name"]
    seq  = session["sequence"]
    for i in range(len(seq) - 1):
        action_a = seq[i]
        action_b = seq[i + 1]
        transition_counts[user][action_a][action_b] += 1
        action_counts[user][action_a] += 1

# ── Convert to probabilities ──────────────────────────────────────────
# Structure: {user: {action_A: [{next: action_B, prob: 0.82, count: 24}]}}
markov_table = {}

for user, actions in transition_counts.items():
    markov_table[user] = {}
    for action_a, nexts in actions.items():
        total = action_counts[user][action_a]
        transitions = []
        for action_b, count in sorted(nexts.items(), key=lambda x: -x[1]):
            if count >= MIN_SUPPORT:
                prob = round(count / total, 3)
                transitions.append({
                    "next_action" : action_b,
                    "probability" : prob,
                    "count"       : count,
                    "total"       : total,
                })
        if transitions:
            markov_table[user][action_a] = transitions

# ── Save JSON ─────────────────────────────────────────────────────────
out_json = os.path.join(BASE_DIR, "output", "markov_table.json")
with open(out_json, "w") as f:
    json.dump(markov_table, f, indent=2)

# ── Save CSV ──────────────────────────────────────────────────────────
rows = []
for user, actions in markov_table.items():
    for action_a, nexts in actions.items():
        for t in nexts:
            rows.append({
                "user"         : user,
                "trigger_action"  : action_a,
                "next_action"  : t["next_action"],
                "probability"  : t["probability"],
                "count"        : t["count"],
                "total_seen"   : t["total"],
            })
csv_out = os.path.join(BASE_DIR, "output", "markov_table.csv")
pd.DataFrame(rows).to_csv(csv_out, index=False)

# ── Print top patterns ────────────────────────────────────────────────
print("=" * 62)
print("  MARKOV TABLE — TOP BEHAVIOUR PATTERNS")
print("=" * 62)

for user in sorted(markov_table.keys()):
    print(f"\n  User: {user}")
    print(f"  {'Trigger Action':<35}  {'Next Action':<30}  Prob")
    print(f"  {'─'*35}  {'─'*30}  {'─'*6}")
    user_rows = [(a, t) for a, ts in markov_table[user].items() for t in ts]
    user_rows.sort(key=lambda x: -x[1]["probability"])
    for action_a, t in user_rows[:10]:
        prob  = t["probability"]
        stars = "★★★" if prob >= 0.75 else ("★★" if prob >= 0.50 else "★")
        print(f"  {action_a:<35}  {t['next_action']:<30}  {prob:.0%}  {stars}")

print()
print(f"  Saved → {out_json}")
print(f"  Saved → {csv_out}")
print()
print("  Next: python 09_behaviour_engine.py")