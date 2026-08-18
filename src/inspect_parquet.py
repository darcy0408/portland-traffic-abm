"""Print one lcap segments parquet's schema so the diagnostic joins correctly."""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

import config

p = os.path.join(config.PROCESSED_DIR,
                 "lcap_realism_reallanes_n16500_s42_segments.parquet")
df = pd.read_parquet(p)
print("columns:", df.columns.tolist())
print("index name:", df.index.name, "| dtype:", df.index.dtype)
print("first 3 index values:", list(df.index[:3]))
print(df.head(3).to_string())
print("rows:", len(df))
