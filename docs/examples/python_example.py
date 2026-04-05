"""
Risk Space MCP — Python analysis example.

This script demonstrates how to load and analyse the published Risk Space
MCP data from a researcher's workstation. It uses only requests + pandas
+ matplotlib so it can run in any scientific Python environment.

Tested with: Python 3.10+, pandas 2.x, matplotlib 3.7+.
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt

BASE_URL = "https://agentic-governance.github.io/risk-space-dashboard/data"


# ---------------------------------------------------------------------------
# Example 1: Load grid risk data
# ---------------------------------------------------------------------------
grid = requests.get(f"{BASE_URL}/grid_risk.json").json()
df = pd.DataFrame(grid)
print(f"Loaded {len(df):,} grid cells")
print(df.head())


# ---------------------------------------------------------------------------
# Example 2: Analyze risk distribution
# ---------------------------------------------------------------------------
print("\n--- expected_harm distribution ---")
print(df["expected_harm"].describe())

fig, ax = plt.subplots(figsize=(8, 5))
df["expected_harm"].hist(bins=50, ax=ax, color="steelblue", edgecolor="white")
ax.set_xlabel("Expected Harm")
ax.set_ylabel("Cell count")
ax.set_title("Risk distribution across all published cells")
plt.tight_layout()
plt.savefig("risk_distribution.png", dpi=150)
print("Saved: risk_distribution.png")


# ---------------------------------------------------------------------------
# Example 3: Find high-risk cells in Tokyo (23 ku bounding box)
# ---------------------------------------------------------------------------
tokyo_mask = (
    df["lat"].between(35.5, 35.85)
    & df["lon"].between(139.5, 139.9)
)
tokyo_df = df[tokyo_mask].sort_values("expected_harm", ascending=False)
print(f"\nTop-20 Tokyo cells by expected_harm "
      f"(n={len(tokyo_df):,} total in bbox):")
print(tokyo_df.head(20))


# ---------------------------------------------------------------------------
# Example 4: Merge with Safe Haven tile index
# ---------------------------------------------------------------------------
haven_idx = requests.get(f"{BASE_URL}/haven_tiles/index.json").json()
print(f"\nTotal haven tiles: {len(haven_idx):,}")


# ---------------------------------------------------------------------------
# Example 5: Join with realtime event markers (last 7 days)
# ---------------------------------------------------------------------------
rt = requests.get(f"{BASE_URL}/realtime_slim.json").json()
rt_df = pd.DataFrame(
    rt, columns=["lat", "lon", "category", "severity", "date"]
)
print(f"\nRealtime events: {len(rt_df):,}")
print(rt_df["category"].value_counts().head(10))

# Spatial join: count events per 0.01° cell
rt_df["cell_lat"] = (rt_df["lat"] * 100).round() / 100
rt_df["cell_lon"] = (rt_df["lon"] * 100).round() / 100
event_counts = (
    rt_df.groupby(["cell_lat", "cell_lon"])
    .size()
    .reset_index(name="n_events")
    .sort_values("n_events", ascending=False)
)
print("\nTop-10 realtime event clusters:")
print(event_counts.head(10))
