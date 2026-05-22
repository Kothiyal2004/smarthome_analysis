import pandas as pd
from datetime import datetime

freq = pd.read_csv("output/pattern_frequency.csv")

def make_notification(row):



    h   = int(row["hour"])
    apm = f"{h % 12 or 12}:00 {'AM' if h < 12 else 'PM'}"
    u   = row["user name"]
    dev = row["device name"].replace("_", " ")
    svc = row["service"].replace("_", " ")

    templates = {
        ("bedroom_ac",       "turn_on"):      f"It's {apm}. Would you like me to turn on the bedroom AC, {u}?",
        ("kitchen_light",    "turn_on"):      f"Good {'morning' if h < 12 else 'evening'} {u}! Shall I turn on the kitchen light?",
        ("front_door_lock",  "lock"):         f"Heading out, {u}? Want me to lock the front door?",
        ("front_door_lock",  "unlock"):       f"Welcome home, {u}! Shall I unlock the front door?",
        ("living_room_tv",   "turn_on"):      f"It's {apm} — your usual TV time, {u}. Turn it on?",
        ("living_room_ac",   "turn_on"):      f"It's {apm}. Shall I cool the living room, {u}?",
        ("bathroom_light",   "turn_on"):      f"Good morning {u}! Want the bathroom light on?",
        ("garage_door",      "open"):         f"Heading out, {u}? Shall I open the garage?",
        ("garage_door",      "close"):        f"Welcome home, {u}! Shall I close the garage?",
        ("bedroom_light",    "turn_on"):      f"It's {apm}. Bedroom light on, {u}?",
        ("smart_thermostat", "set_temperature"): f"Setting the thermostat to your usual temp, {u}?",
    }
    key = (row["device name"], row["service"])
    return templates.get(key, f"{apm}: {svc} {dev} for {u}?")

# Filter HIGH + MEDIUM confidence only


triggers = freq[freq["confidence"].isin(["HIGH","MEDIUM"])].copy()
# triggers = triggers.sort_values(["User Name","pct"], ascending=[True, False])
triggers = triggers.sort_values(["user name","pct"], ascending=[True, False])
triggers["notification"] = triggers.apply(make_notification, axis=1)

print("=" * 65)
print("  SMART NOTIFICATION TRIGGERS")
print("=" * 65)

for user, group in triggers.groupby("user name"):
    print(f"\n--- {user} ---")
    for _, row in group.iterrows():
        h   = int(row["hour"])
        apm = f"{h%12 or 12}:00 {'AM' if h < 12 else 'PM'}"
        print(f"  [{apm}]  {row['device name'].replace('_',' ')}"
              f"  |  {row['service'].replace('_',' ')}"
              f"  |  {row['pct']}% ({row['confidence']})")
        print(f"  → {row['notification']}")

triggers.to_csv("output/notifications.csv", index=False)
print("\nSaved: output/notifications.csv")