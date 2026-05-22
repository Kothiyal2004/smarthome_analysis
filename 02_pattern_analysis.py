import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_csv("output/cleaned_logs.csv")

df.columns = df.columns.str.strip().str.lower()
df = df.loc[:, ~df.columns.duplicated()]

df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")




# df = pd.read_csv("output/cleaned_logs.csv")

# # Normalize column names
# df.columns = df.columns.str.strip().str.lower()

# df["timestamp"] = pd.to_datetime(df["timestamp"])

# ── STEP 1: Count events ──
freq = (df
        .groupby(["user name","device name","service","hour"])
        .size()
        .reset_index(name="count"))

freq["pct"] = (freq["count"] / 31 * 100).round(1)
freq["confidence"] = freq["pct"].apply(
    lambda p: "HIGH" if p >= 55 else ("MEDIUM" if p >= 40 else "LOW"))

print("=== Top patterns found ===")
top = freq.sort_values("pct", ascending=False).head(15)
print(top.to_string())

# ── STEP 2: Heatmap ──
alice_ac = df[(df["user name"]=="Alice") &
              (df["device name"]=="bedroom_ac") &
              (df["service"]=="turn_on")].copy()

alice_ac["date"] = pd.to_datetime(alice_ac["date"])

pivot = alice_ac.groupby(["date","hour"]).size().unstack(fill_value=0)
pivot = pivot.reindex(columns=range(24), fill_value=0)

plt.figure(figsize=(16, 6))
sns.heatmap(pivot, cmap="Blues", linewidths=0.3,
            cbar_kws={"label": "Events"})
plt.title("Alice — Bedroom AC turn_on — by date and hour")
plt.xlabel("Hour of day")
plt.ylabel("Date")
plt.tight_layout()
plt.savefig("output/heatmap_alice_ac.png", dpi=150)
plt.close()

print("\nSaved: output/heatmap_alice_ac.png")

# ── STEP 3: Save results ──
freq.to_csv("output/pattern_frequency.csv", index=False)
print("Saved: output/pattern_frequency.csv")