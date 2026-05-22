"""
10_pattern_report.py
────────────────────────────────────────────────────────
Generates a visual HTML report showing:
  1. Session activity heatmap per user (hour vs day)
  2. Top behaviour patterns per user
  3. Markov transition table as a chart
  4. Top predictions the engine will fire
  5. Behaviour type breakdown

Opens automatically in your browser when done.

Usage:
    python 10_pattern_report.py
────────────────────────────────────────────────────────
"""

import pandas as pd
import json
import os
import webbrowser
from collections import Counter
from datetime import datetime

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
OUT_DIR    = os.path.join(BASE_DIR, "output")
REPORT_PATH = os.path.join(OUT_DIR, "pattern_report.html")

# ── Load all data ─────────────────────────────────────
def load_file(name, kind="csv"):
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        return None
    if kind == "json":
        with open(path) as f:
            return json.load(f)
    return pd.read_csv(path)

sessions_raw = load_file("sessions.json", "json")
sessions_df  = load_file("sessions.csv")
summary_df   = load_file("session_summary.csv")
markov_raw   = load_file("markov_table.json", "json")
markov_df    = load_file("markov_table.csv")
freq_df      = load_file("pattern_frequency.csv")

if sessions_raw is None:
    print("ERROR: sessions.json not found. Run 07_session_builder.py first.")
    raise SystemExit(1)
if markov_raw is None:
    print("ERROR: markov_table.json not found. Run 08_markov_builder.py first.")
    raise SystemExit(1)

print(f"Loaded {len(sessions_raw)} sessions")
print(f"Loaded markov table for users: {list(markov_raw.keys())}")

# ── Compute stats ─────────────────────────────────────
users = sorted({s["user_name"] for s in sessions_raw})
USER_COLORS = {
    users[0]: "#185FA5",
    users[1] if len(users) > 1 else "": "#1F7A4A",
    users[2] if len(users) > 2 else "": "#6B1F8B",
}
USER_LIGHT = {
    users[0]: "#EBF3FB",
    users[1] if len(users) > 1 else "": "#E1F5EE",
    users[2] if len(users) > 2 else "": "#F3EBF9",
}

def user_color(u):  return USER_COLORS.get(u, "#1F3864")
def user_light(u):  return USER_LIGHT.get(u, "#EBF3FB")

# Per-user stats
user_stats = {}
for u in users:
    u_ses = [s for s in sessions_raw if s["user_name"] == u]
    behaviours = Counter(s["behaviour"] for s in u_ses)
    # Hour activity
    hour_counts = Counter()
    for s in u_ses:
        hour_counts[s["hour_start"]] += s["n_events"]
    # Top transitions
    transitions = []
    if u in markov_raw:
        for action_a, nexts in markov_raw[u].items():
            for t in nexts:
                transitions.append({
                    "from": action_a,
                    "to":   t["next_action"],
                    "prob": t["probability"],
                    "count": t["count"],
                })
    transitions.sort(key=lambda x: -x["prob"])
    user_stats[u] = {
        "total_sessions": len(u_ses),
        "behaviours":     dict(behaviours),
        "hour_counts":    dict(hour_counts),
        "transitions":    transitions[:10],
        "avg_length":     sum(s["n_events"] for s in u_ses) / max(len(u_ses), 1),
    }

# ── Build HTML ────────────────────────────────────────
def stars(p):
    if p >= 0.75: return "★★★"
    if p >= 0.50: return "★★"
    return "★"

def badge_color(p):
    if p >= 0.75: return "#EAF3DE;color:#27500A"
    if p >= 0.50: return "#FFF2CC;color:#633806"
    return "#FCE4D6;color:#993C1D"

def make_bar(val, max_val, color, height=20):
    w = int(val / max(max_val, 1) * 100)
    return (f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:{w}%;height:{height}px;background:{color};'
            f'border-radius:3px;min-width:2px"></div>'
            f'<span style="font-size:11px;color:#555">{val}</span></div>')

# Heatmap data per user
def heatmap_grid(u):
    u_ses = [s for s in sessions_raw if s["user_name"] == u]
    grid  = {}  # (date, hour) -> count
    for s in u_ses:
        key = (s["date"], s["hour_start"])
        grid[key] = grid.get(key, 0) + s["n_events"]
    dates = sorted({s["date"] for s in u_ses})
    hours = list(range(24))
    max_v = max(grid.values()) if grid else 1
    color = user_color(u)
    cr, cg, cb = int(color[1:3],16), int(color[3:5],16), int(color[5:7],16)

    rows_html = ""
    for date in dates:
        cells = ""
        for h in hours:
            v = grid.get((date, h), 0)
            if v:
                alpha = 0.15 + (v / max_v) * 0.75
                nr = int(255-(255-cr)*alpha)
                ng = int(255-(255-cg)*alpha)
                nb = int(255-(255-cb)*alpha)
                bg = f"rgb({nr},{ng},{nb})"
                fc = "#fff" if alpha > 0.55 else "#333"
                cells += (f'<td style="background:{bg};color:{fc};'
                          f'width:28px;height:16px;text-align:center;'
                          f'font-size:9px;font-family:monospace">{v}</td>')
            else:
                cells += ('<td style="background:#F8F9FA;width:28px;'
                          'height:16px"></td>')
        rows_html += f'<tr><td style="font-size:10px;white-space:nowrap;padding-right:6px;color:#666">{date}</td>{cells}</tr>'

    hour_headers = "".join(
        f'<th style="font-size:9px;font-weight:500;color:#888;width:28px;text-align:center">{h:02d}</th>'
        for h in hours)

    return (f'<div style="overflow-x:auto"><table style="border-collapse:collapse">'
            f'<tr><th style="width:80px"></th>{hour_headers}</tr>'
            f'{rows_html}</table></div>')

# Behaviour chart per user
def behaviour_chart(u):
    beh   = user_stats[u]["behaviours"]
    total = sum(beh.values())
    if not total:
        return "<p>No data</p>"
    BEH_COLORS = {
        "arriving_home":   "#185FA5",
        "leaving_home":    "#854F0B",
        "morning_routine": "#3B6D11",
        "night_routine":   "#534AB7",
        "comfort_control": "#0F6E56",
        "general":         "#888",
    }
    html = '<div style="display:flex;flex-direction:column;gap:5px">'
    for b, cnt in sorted(beh.items(), key=lambda x: -x[1]):
        pct = cnt / total * 100
        col = BEH_COLORS.get(b, "#888")
        html += (f'<div style="display:flex;align-items:center;gap:8px">'
                 f'<div style="font-size:11px;min-width:130px;color:#444">{b.replace("_"," ")}</div>'
                 f'<div style="flex:1;height:16px;background:#eee;border-radius:3px;overflow:hidden">'
                 f'<div style="width:{pct:.0f}%;height:100%;background:{col};border-radius:3px"></div></div>'
                 f'<div style="font-size:11px;color:#666;min-width:40px">{cnt} ({pct:.0f}%)</div>'
                 f'</div>')
    html += '</div>'
    return html

# Transition table per user
def transition_table(u):
    trans = user_stats[u]["transitions"]
    if not trans:
        return "<p>No transitions found</p>"
    html = ('<table style="width:100%;border-collapse:collapse;font-size:12px">'
            '<tr style="background:#1F3864;color:#fff">'
            '<th style="padding:7px 10px;text-align:left">When user does this</th>'
            '<th style="padding:7px 10px;text-align:left">Predict next action</th>'
            '<th style="padding:7px 10px;text-align:center">Probability</th>'
            '<th style="padding:7px 10px;text-align:center">Seen</th>'
            '</tr>')
    for i, t in enumerate(trans):
        bg = "#F8F9FA" if i % 2 else "#FFFFFF"
        bc = badge_color(t["prob"])
        html += (f'<tr style="background:{bg}">'
                 f'<td style="padding:6px 10px;color:#333;font-family:monospace;font-size:11px">{t["from"]}</td>'
                 f'<td style="padding:6px 10px;color:#185FA5;font-family:monospace;font-size:11px">{t["to"]}</td>'
                 f'<td style="padding:6px 10px;text-align:center">'
                 f'<span style="background:{bc};padding:2px 8px;border-radius:10px;font-weight:500">'
                 f'{t["prob"]:.0%}  {stars(t["prob"])}</span></td>'
                 f'<td style="padding:6px 10px;text-align:center;color:#888">{t["count"]}x</td>'
                 f'</tr>')
    html += '</table>'
    return html

# Top predictions summary
def top_predictions():
    rows = []
    for u in users:
        for t in user_stats[u]["transitions"]:
            if t["prob"] >= 0.60:
                dev = t["to"].split("::")[0].replace("_"," ")
                svc = t["to"].split("::")[-1].replace("_"," ") if "::" in t["to"] else ""
                trigger_dev = t["from"].split("::")[0].replace("_"," ")
                trigger_svc = t["from"].split("::")[-1].replace("_"," ") if "::" in t["from"] else ""
                rows.append((u, t["from"], t["to"], t["prob"],
                             f'After {trigger_dev} {trigger_svc} — shall I {svc} the {dev}?'))
    rows.sort(key=lambda x: -x[3])
    if not rows:
        return "<p>No high-confidence predictions found.</p>"
    html = ('<table style="width:100%;border-collapse:collapse;font-size:12px">'
            '<tr style="background:#1F3864;color:#fff">'
            '<th style="padding:7px 10px;text-align:left">User</th>'
            '<th style="padding:7px 10px;text-align:left">Trigger</th>'
            '<th style="padding:7px 10px;text-align:left">Predicted next</th>'
            '<th style="padding:7px 10px;text-align:center">Confidence</th>'
            '<th style="padding:7px 10px;text-align:left">Suggestion</th>'
            '</tr>')
    for i, (u, frm, to, prob, msg) in enumerate(rows[:15]):
        bg = "#F8F9FA" if i % 2 else "#FFFFFF"
        bc = badge_color(prob)
        html += (f'<tr style="background:{bg}">'
                 f'<td style="padding:6px 10px"><span style="background:{user_light(u)};'
                 f'color:{user_color(u)};padding:2px 8px;border-radius:10px;'
                 f'font-weight:500;font-size:11px">{u}</span></td>'
                 f'<td style="padding:6px 10px;font-family:monospace;font-size:11px;color:#444">{frm}</td>'
                 f'<td style="padding:6px 10px;font-family:monospace;font-size:11px;color:#185FA5">{to}</td>'
                 f'<td style="padding:6px 10px;text-align:center">'
                 f'<span style="background:{bc};padding:2px 8px;border-radius:10px;font-weight:500">'
                 f'{prob:.0%}</span></td>'
                 f'<td style="padding:6px 10px;font-size:11px;color:#333;font-style:italic">"{msg}"</td>'
                 f'</tr>')
    html += '</table>'
    return html

# ── Assemble full HTML ────────────────────────────────
now = datetime.now().strftime("%Y-%m-%d %H:%M")

user_sections = ""
for u in users:
    col   = user_color(u)
    light = user_light(u)
    stats = user_stats[u]
    user_sections += f"""
    <div style="margin-bottom:2.5rem">
      <h2 style="color:{col};border-bottom:2px solid {col};padding-bottom:.4rem;margin-bottom:1.25rem">
        {u}
        <span style="font-size:13px;font-weight:400;color:#666;margin-left:12px">
          {stats['total_sessions']} sessions &nbsp;·&nbsp;
          avg {stats['avg_length']:.1f} events/session
        </span>
      </h2>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-bottom:1.25rem">
        <div>
          <h3 style="font-size:13px;font-weight:500;color:#333;margin:0 0 .6rem">
            Behaviour types
          </h3>
          {behaviour_chart(u)}
        </div>
        <div>
          <h3 style="font-size:13px;font-weight:500;color:#333;margin:0 0 .6rem">
            Activity by hour (events per session)
          </h3>
          <div style="display:flex;gap:2px;align-items:flex-end;height:60px">
            {"".join(
              f'<div style="flex:1;background:{col};opacity:{0.2 + stats["hour_counts"].get(h,0)/max(stats["hour_counts"].values() or [1])*0.8:.2f};'
              f'height:{int(stats["hour_counts"].get(h,0)/max(stats["hour_counts"].values() or [1])*100)}%;'
              f'min-height:2px;border-radius:2px 2px 0 0" title="{h:02d}:00 — {stats["hour_counts"].get(h,0)} events"></div>'
              for h in range(24)
            )}
          </div>
          <div style="display:flex;justify-content:space-between;font-size:9px;color:#aaa;margin-top:2px">
            <span>00</span><span>06</span><span>12</span><span>18</span><span>23</span>
          </div>
        </div>
      </div>

      <h3 style="font-size:13px;font-weight:500;color:#333;margin:.5rem 0 .6rem">
        What {u} does next — Markov transitions
      </h3>
      {transition_table(u)}

      <h3 style="font-size:13px;font-weight:500;color:#333;margin:1rem 0 .6rem">
        Session heatmap — activity across 31 days
      </h3>
      <p style="font-size:11px;color:#888;margin:0 0 .4rem">
        Rows = dates &nbsp;·&nbsp; Columns = hours (00–23) &nbsp;·&nbsp;
        Darker = more events &nbsp;·&nbsp; Dark column = strong pattern
      </p>
      {heatmap_grid(u)}
    </div>
    """

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Smart Home — Pattern Report</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    margin:0;padding:0;background:#F5F7FA;color:#222}}
  .header{{background:#1F3864;color:#fff;padding:1.5rem 2rem}}
  .header h1{{margin:0;font-size:22px;font-weight:500}}
  .header p{{margin:.25rem 0 0;opacity:.7;font-size:13px}}
  .container{{max-width:1200px;margin:0 auto;padding:2rem}}
  .section{{background:#fff;border-radius:10px;padding:1.5rem 2rem;
    margin-bottom:1.5rem;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
  .section h2{{margin:0 0 1rem;font-size:18px}}
  .stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
    gap:1rem;margin-bottom:1.5rem}}
  .stat-card{{background:#F8F9FA;border-radius:8px;padding:.9rem 1.1rem}}
  .stat-val{{font-size:26px;font-weight:500;color:#1F3864}}
  .stat-lbl{{font-size:12px;color:#888;margin-top:3px}}
</style>
</head>
<body>

<div class="header">
  <h1>Smart Home — Behaviour Pattern Report</h1>
  <p>Generated {now} &nbsp;·&nbsp;
     {len(sessions_raw)} sessions &nbsp;·&nbsp;
     {len(users)} users &nbsp;·&nbsp;
     Markov chain predictions</p>
</div>

<div class="container">

  <div class="section">
    <h2 style="color:#1F3864">Summary</h2>
    <div class="stat-grid">
      <div class="stat-card"><div class="stat-val">{len(sessions_raw)}</div>
        <div class="stat-lbl">Total sessions</div></div>
      <div class="stat-card"><div class="stat-val">{len(users)}</div>
        <div class="stat-lbl">Users analysed</div></div>
      <div class="stat-card">
        <div class="stat-val">{sum(len(v) for v in markov_raw.values())}</div>
        <div class="stat-lbl">Transition patterns</div></div>
      <div class="stat-card">
        <div class="stat-val">{sum(1 for u in users for t in user_stats[u]["transitions"] if t["prob"]>=0.60)}</div>
        <div class="stat-lbl">High-confidence predictions</div></div>
    </div>
  </div>

  <div class="section">
    <h2 style="color:#1F3864">Top predictions — what the engine will suggest</h2>
    <p style="font-size:12px;color:#888;margin:0 0 .75rem">
      These are the suggestions that fire when a trigger action is detected.
      Confidence ≥ 60% = system fires a suggestion.
    </p>
    {top_predictions()}
  </div>

  <div class="section">
    <h2 style="color:#1F3864">Per-user behaviour patterns</h2>
    {user_sections}
  </div>

</div>
</body>
</html>"""

with open(REPORT_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Report saved → {REPORT_PATH}")
print("Opening in browser...")
webbrowser.open(f"file://{REPORT_PATH}")
print("Done.")