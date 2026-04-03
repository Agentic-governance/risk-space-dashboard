#!/usr/bin/env python3
"""
Task 2: Spatiotemporal KDE for crime risk estimation.

Uses scipy.ndimage.gaussian_filter on a 2D histogram grid.
Produces normalized density (0-1) over the Tokyo area.
"""

import json
import math
import numpy as np
from datetime import datetime, timezone, timedelta
from scipy.ndimage import gaussian_filter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data" / "normalized"

# ---------------------------------------------------------------------------
# Core KDE function
# ---------------------------------------------------------------------------

def calc_spatial_kde(events, grid_lat, grid_lon, bandwidth=0.01):
    """
    Compute spatial KDE via 2D histogram + gaussian_filter.

    Parameters
    ----------
    events : list of (lon, lat) tuples
    grid_lat : 1-D array of latitude bin edges
    grid_lon : 1-D array of longitude bin edges
    bandwidth : float, in degrees – converted to filter sigma in grid cells

    Returns
    -------
    density : 2-D ndarray (len(grid_lat)-1 x len(grid_lon)-1), normalised 0-1
    """
    lons = np.array([e[0] for e in events])
    lats = np.array([e[1] for e in events])

    # Build 2D histogram (lat = rows, lon = cols)
    hist, _, _ = np.histogram2d(
        lats, lons,
        bins=[grid_lat, grid_lon],
    )

    # Convert bandwidth (degrees) to sigma in grid-cell units
    lat_res = grid_lat[1] - grid_lat[0]
    lon_res = grid_lon[1] - grid_lon[0]
    sigma_lat = bandwidth / lat_res
    sigma_lon = bandwidth / lon_res

    smoothed = gaussian_filter(hist, sigma=[sigma_lat, sigma_lon])

    # Normalize to 0-1
    vmax = smoothed.max()
    if vmax > 0:
        smoothed /= vmax

    return smoothed


def calc_spatial_kde_weighted(events, weights, grid_lat, grid_lon, bandwidth=0.01):
    """
    Weighted spatial KDE – each event contributes its weight to the histogram.
    """
    lons = np.array([e[0] for e in events])
    lats = np.array([e[1] for e in events])
    w = np.array(weights)

    hist, _, _ = np.histogram2d(
        lats, lons,
        bins=[grid_lat, grid_lon],
        weights=w,
    )

    lat_res = grid_lat[1] - grid_lat[0]
    lon_res = grid_lon[1] - grid_lon[0]
    sigma_lat = bandwidth / lat_res
    sigma_lon = bandwidth / lon_res

    smoothed = gaussian_filter(hist, sigma=[sigma_lat, sigma_lon])

    vmax = smoothed.max()
    if vmax > 0:
        smoothed /= vmax

    return smoothed


# ---------------------------------------------------------------------------
# Time-weighted helpers
# ---------------------------------------------------------------------------

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 4, 4, tzinfo=JST)


def parse_time(ts):
    """Parse ISO timestamp, return datetime (tz-aware)."""
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def time_weight(dt, half_life_days=30):
    """Exponential decay weight based on days ago."""
    if dt is None:
        return 0.0
    days_ago = (NOW - dt).total_seconds() / 86400
    if days_ago < 0:
        days_ago = 0
    return math.exp(-days_ago / half_life_days)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # --- Load events ---
    crime_path = DATA_DIR / "crime_all.json"
    print(f"Loading {crime_path} ...")
    with open(crime_path) as f:
        raw = json.load(f)

    # Filter to events with coordinates
    events_coords = []
    events_times = []
    for ev in raw:
        geom = ev.get("geometry")
        if not geom or not geom.get("coordinates"):
            continue
        lon, lat = geom["coordinates"]
        if lon is None or lat is None:
            continue
        events_coords.append((lon, lat))
        events_times.append(parse_time(ev.get("occurred_at")))

    print(f"Events with coordinates: {len(events_coords)}")

    # --- Grid definition: Tokyo area ---
    lat_min, lat_max = 35.5, 35.9
    lon_min, lon_max = 139.5, 139.9
    resolution = 0.002  # ~200m

    grid_lat = np.arange(lat_min, lat_max + resolution, resolution)
    grid_lon = np.arange(lon_min, lon_max + resolution, resolution)

    print(f"Grid: {len(grid_lat)-1} lat bins x {len(grid_lon)-1} lon bins  "
          f"(resolution={resolution}°)")

    # --- Basic (uniform-weight) KDE ---
    print("\n=== Basic Spatial KDE ===")
    density = calc_spatial_kde(events_coords, grid_lat, grid_lon, bandwidth=0.01)
    print(f"Density shape: {density.shape}")
    print(f"Max density: {density.max():.4f}  (should be 1.0)")
    print(f"Mean density: {density.mean():.6f}")
    nonzero = (density > 0.01).sum()
    print(f"Cells > 0.01: {nonzero}  ({100*nonzero/density.size:.1f}%)")

    # Find peak location
    peak_idx = np.unravel_index(density.argmax(), density.shape)
    peak_lat = grid_lat[peak_idx[0]] + resolution / 2
    peak_lon = grid_lon[peak_idx[1]] + resolution / 2
    print(f"Peak at lat={peak_lat:.4f}, lon={peak_lon:.4f}")

    # --- Time-weighted KDE ---
    print("\n=== Time-Weighted KDE (half-life=30 days) ===")
    weights = [time_weight(t, half_life_days=30) for t in events_times]
    nonzero_w = sum(1 for w in weights if w > 0.001)
    print(f"Events with meaningful weight (>0.001): {nonzero_w}")

    density_tw = calc_spatial_kde_weighted(
        events_coords, weights, grid_lat, grid_lon, bandwidth=0.01
    )
    print(f"Time-weighted density shape: {density_tw.shape}")
    print(f"Mean density: {density_tw.mean():.6f}")

    peak_idx_tw = np.unravel_index(density_tw.argmax(), density_tw.shape)
    peak_lat_tw = grid_lat[peak_idx_tw[0]] + resolution / 2
    peak_lon_tw = grid_lon[peak_idx_tw[1]] + resolution / 2
    print(f"Time-weighted peak at lat={peak_lat_tw:.4f}, lon={peak_lon_tw:.4f}")

    # --- Save result ---
    out = {
        "lat_min": lat_min,
        "lat_max": lat_max,
        "lon_min": lon_min,
        "lon_max": lon_max,
        "resolution": resolution,
        "density": density.tolist(),
    }
    out_path = DATA_DIR / "kde_tokyo.json"
    with open(out_path, "w") as f:
        json.dump(out, f)
    size_mb = out_path.stat().st_size / 1e6
    print(f"\nSaved to {out_path}  ({size_mb:.1f} MB)")

    # --- Summary stats ---
    print("\n=== Summary ===")
    # Top-5 hotspot cells
    flat = density.flatten()
    top5 = np.argsort(flat)[-5:][::-1]
    print("Top-5 hotspot cells:")
    for rank, idx in enumerate(top5, 1):
        r, c = np.unravel_index(idx, density.shape)
        lat = grid_lat[r] + resolution / 2
        lon = grid_lon[c] + resolution / 2
        print(f"  {rank}. lat={lat:.4f} lon={lon:.4f}  density={density[r,c]:.4f}")


if __name__ == "__main__":
    main()
