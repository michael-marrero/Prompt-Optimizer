import pickle
import pandas as pd

INPUT_PKL = "routerbench_0shot.pkl"
OUTPUT_CSV = "routerbench.csv"

with open(INPUT_PKL, "rb") as f:
    obj = pickle.load(f)

if isinstance(obj, pd.DataFrame):
    df = obj
else:
    # try converting
    df = pd.DataFrame(obj)

df.to_csv(OUTPUT_CSV, index=False)

print(f"Saved CSV to: {OUTPUT_CSV}")

df = pd.read_pickle("routerbench_0shot.pkl")

# Remove trailing numbers (and optional separator before them)
clean_ids = df["sample_id"].str.replace(r"[\._-]?\d+$", "", regex=True)

unique_clean = clean_ids.unique()

print(f"Total unique (numbers removed): {len(unique_clean)}\n")

for uid in unique_clean:
    print(uid)