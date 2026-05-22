import pandas as pd

df = pd.read_excel(
    "data/smart_home_pattern_dataset.xlsx",
    sheet_name="Raw Logs",
    header=1   # 👈 likely correct
)
# Clean column names
df.columns = df.columns.str.strip()

# Debug: see actual column names
print(df.columns.tolist())

# Now try conversion
df["timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
# df["timestamp"] = pd.to_datetime(df["Timestamp"])

# # Load the Raw Logs sheet from your Excel file
# df = pd.read_excel("data/smart_home_pattern_dataset.xlsx",
#                    sheet_name="Raw Logs")

# df.columns = df.columns.str.strip()

# df["timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

# Remove invalid rows
df = df.dropna(subset=["timestamp"])

# Convert timestamp to datetime
# df["timestamp"] = pd.to_datetime(df["Timestamp"])
df["hour"]      = df["timestamp"].dt.hour
df["date"]      = df["timestamp"].dt.date
df["weekday"]   = df["timestamp"].dt.day_name()

print("=== Dataset loaded ===")
print(f"Total log rows : {len(df)}")
print(f"Date range     : {df['date'].min()} → {df['date'].max()}")
print(f"Users          : {df['User Name'].unique()}")
print(f"Devices        : {df['Device Name'].unique()}")
print()
print("=== Sample rows ===")
print(df[["Timestamp","User Name","Device Name","Service"]].head(10).to_string())

# Save cleaned version for next scripts
df.to_csv("output/cleaned_logs.csv", index=False)
print("\nSaved: output/cleaned_logs.csv")