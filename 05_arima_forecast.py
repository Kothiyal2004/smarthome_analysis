"""
05_arima_forecast.py  (v5 — final)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import warnings, os
from datetime import timedelta

warnings.filterwarnings("ignore")
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "output", "cleaned_logs.csv")

# ── Load ──────────────────────────────────────────────────────────────
raw = pd.read_csv(CSV_PATH)

# Find timestamp column BEFORE renaming anything
ts_col_raw = next(
    (c for c in raw.columns if c.strip().lower() == "timestamp"), None
)
if ts_col_raw is None:
    print("ERROR: no timestamp column. Columns:", list(raw.columns))
    raise SystemExit(1)

# Parse the ONE timestamp Series — .astype(str) prevents the
# "assemble from unit mappings" bug that fires when pandas sees
# columns named day, hour, etc. alongside the datetime conversion
ts_series = pd.to_datetime(raw[ts_col_raw].astype(str), errors="coerce")

# Build a clean working DataFrame — only the columns we need
df = pd.DataFrame({
    "timestamp":   ts_series,
    "user_name":   raw[[c for c in raw.columns if "user" in c.lower() and "name" in c.lower()][0]],
    "device_name": raw[[c for c in raw.columns if "device" in c.lower() and "name" in c.lower()][0]],
    "service":     raw[[c for c in raw.columns if c.strip().lower() == "service"][0]],
})

# Drop unparseable rows
df = df.dropna(subset=["timestamp"])

# Extract hour and date
df["_hour"] = df["timestamp"].dt.hour
df["_date"] = df["timestamp"].dt.date   # plain Python date objects — safe for groupby

print(f"  Loaded {len(df)} rows  (timestamp range: "
      f"{df['timestamp'].min().date()} -> {df['timestamp'].max().date()})")
print()

# ── Filter ────────────────────────────────────────────────────────────
alice_ac = df[
    df["user_name"].astype(str).str.lower().str.contains("alice", na=False) &
    df["device_name"].astype(str).str.lower().str.contains("bedroom_ac", na=False) &
    (df["service"].astype(str).str.lower() == "turn_on")
].copy()

print(f"  Alice bedroom_ac turn_on events: {len(alice_ac)}")
if len(alice_ac) < 7:
    print("  Need at least 7 days of data. Run more days or connect real HA data.")
    raise SystemExit(0)

# ── One row per day ───────────────────────────────────────────────────
# groupby on plain date objects — guaranteed no ambiguity
by_day    = alice_ac.groupby("_date")["_hour"].min()
hours_arr = by_day.values.astype(np.float64)
n_days    = int(len(by_day))
mean_h    = float(np.mean(hours_arr))
dmin      = str(min(by_day.index))
dmax      = str(max(by_day.index))

print("=" * 56)
print("  ALICE — BEDROOM AC — DAILY TURN-ON HOUR")
print("=" * 56)
print(f"  Days with data : {n_days}")
print(f"  Date range     : {dmin} -> {dmax}")
print(f"  Mean hour      : {mean_h:.1f}h")
print()

# ── Stationarity ──────────────────────────────────────────────────────
adf_p   = float(adfuller(hours_arr)[1])
d_order = 0 if adf_p < 0.05 else 1
print(f"  ADF p-value = {adf_p:.4f}  ->  d = {d_order}")
print()

# ── ARIMA — use plain integer index to avoid ALL datetime freq issues ──
# ARIMA doesn't need dates — it only needs the sequence of values.
# We'll map results back to real dates ourselves.
model  = ARIMA(hours_arr, order=(1, d_order, 1))
result = model.fit()
print(f"  ARIMA(1,{d_order},1) fitted  |  AIC = {float(result.aic):.1f}")
print()

# ── Forecast helpers ──────────────────────────────────────────────────
def clamp(v):
    return float(max(0.0, min(23.0, float(v))))

def ampm(h):
    h = int(round(clamp(h)))
    return f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}"

# ── Tomorrow ──────────────────────────────────────────────────────────
fc1    = result.get_forecast(steps=1)
pred_h = int(round(clamp(float(fc1.predicted_mean[0]))))
ci1    = fc1.conf_int(alpha=0.05)
ci_lo  = round(clamp(float(ci1[0, 0])), 1)
ci_hi  = round(clamp(float(ci1[0, 1])), 1)

print("=" * 56)
print("  FORECAST — TOMORROW")
print("=" * 56)
print(f"  Predicted hour : {pred_h:02d}:00  ({ampm(pred_h)})")
print(f"  95% CI         : {ci_lo}h - {ci_hi}h")
print()
print(f'  NOTIFICATION: "It\'s {ampm(pred_h)}. Would you like me')
print(f'                to turn on the bedroom AC, Alice?"')
print()

# ── 7-day ─────────────────────────────────────────────────────────────
fc7  = result.get_forecast(steps=7)
p7v  = fc7.predicted_mean          # numpy array (integer indexed)
ci7v = fc7.conf_int(alpha=0.05)    # numpy 2d array

# Real future dates — compute from the last known date
last_date = max(by_day.index)   # plain Python date
future_dates = [
    last_date + timedelta(days=i + 1) for i in range(7)
]

print("=" * 56)
print("  7-DAY FORECAST")
print("=" * 56)
print(f"  {'Date':<14}  {'Hour':<14}  95% CI")
print(f"  {'-'*14}  {'-'*14}  {'-'*16}")

rows = []
for i in range(7):
    fdate = str(future_dates[i])
    fhour = int(round(clamp(float(p7v[i]))))
    flo   = round(clamp(float(ci7v[i, 0])), 1)
    fhi   = round(clamp(float(ci7v[i, 1])), 1)
    print(f"  {fdate:<14}  {fhour:02d}:00 ({ampm(fhour):<8})  {flo}h - {fhi}h")
    rows.append({
        "date": fdate, "user": "Alice",
        "device": "bedroom_ac", "service": "turn_on",
        "predicted_hour": fhour, "ci_low": flo, "ci_high": fhi,
        "notification": (
            f"It's {ampm(fhour)}. Would you like me to "
            f"turn on the bedroom AC, Alice?"
        )
    })
print()

# ── Save CSV ──────────────────────────────────────────────────────────
fc_csv = os.path.join(BASE_DIR, "output", "arima_forecast.csv")
pd.DataFrame(rows).to_csv(fc_csv, index=False)
print(f"  Saved -> {fc_csv}")

# ── Chart ─────────────────────────────────────────────────────────────
observed_dates = [pd.Timestamp(str(d)) for d in by_day.index]
future_ts      = [pd.Timestamp(str(d)) for d in future_dates]
fitted_vals    = result.fittedvalues   # numpy array, same length as input

fig, ax = plt.subplots(figsize=(14, 5))
fig.patch.set_facecolor("white")
ax.set_facecolor("#F8FAFD")

ax.plot(observed_dates, hours_arr,
        "o", color="#378ADD", markersize=5, alpha=0.8, label="Observed")
ax.plot(observed_dates, fitted_vals,
        color="#1D9E75", linewidth=1.5, alpha=0.7, label="ARIMA fitted")
ax.plot(future_ts, [clamp(v) for v in p7v],
        "o--", color="#378ADD", linewidth=1.5, markersize=7, label="Forecast")
ax.fill_between(future_ts,
    np.clip(ci7v[:, 0], 0, 23),
    np.clip(ci7v[:, 1], 0, 23),
    color="#378ADD", alpha=0.15, label="95% CI")

ax.axvline(observed_dates[-1], color="#888780",
           linewidth=0.8, linestyle="--", alpha=0.6)
ax.text(observed_dates[-1], 23.3, " forecast ->",
        fontsize=9, color="#5F5E5A", va="top")

ax.set_title("Alice — bedroom AC: history & ARIMA 7-day forecast",
             fontsize=12, pad=10)
ax.set_ylabel("Hour of day")
ax.set_xlabel("Date")
ax.set_ylim(14, 24)
ax.set_yticks(range(15, 24))
ax.set_yticklabels([f"{h:02d}:00" for h in range(15, 24)])
ax.grid(axis="y", alpha=0.4, linewidth=0.5)
ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

plt.tight_layout()
chart_path = os.path.join(BASE_DIR, "output", "arima_forecast_alice_ac.png")
plt.savefig(chart_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"  Chart  -> {chart_path}")
print()
print("  All done.")
print()
print("  Schedule nightly:")
print("  crontab -e")
print("  1 0 * * *  cd ~/Desktop/smarthome_analysis && \\")
print("             venv/bin/python 05_arima_forecast.py >> output/arima.log 2>&1")