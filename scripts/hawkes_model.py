#!/usr/bin/env python3
"""
Task 9: Spatio-Temporal Hawkes Process model for crime risk prediction.

Implements:
- SpatioTemporalHawkes class (intensity, predict_risk)
- blend_risk function (KDE + Hawkes fusion)
- Synthetic event test around Shinjuku
"""

import math
import numpy as np
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Hawkes Process
# ---------------------------------------------------------------------------

class SpatioTemporalHawkes:
    """
    Self-exciting point process for spatio-temporal crime risk.

    Parameters
    ----------
    mu    : float – background intensity (events per day per unit area)
    K     : float – excitation coefficient (0 < K < 1 for stability)
    omega : float – temporal decay rate (1/days), default 1/14 ≈ 0.071
    sigma : float – spatial spread in km
    """

    def __init__(self, mu=0.05, K=0.3, omega=1/14, sigma=0.5):
        self.mu = mu
        self.K = K
        self.omega = omega
        self.sigma = sigma

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        """Great-circle distance in km."""
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dlon / 2) ** 2)
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def intensity(self, t, x, y, history):
        """
        Conditional intensity at (t, x=lat, y=lon).

        history : list of (t_i, lat_i, lon_i) – past events (t_i < t)

        Returns λ(t, x, y)
        """
        lam = self.mu

        for t_i, lat_i, lon_i in history:
            dt = t - t_i
            if dt <= 0:
                continue
            # Temporal kernel: omega * exp(-omega * dt)
            temporal = self.omega * math.exp(-self.omega * dt)
            # Spatial kernel: Gaussian on distance
            d_km = self._haversine_km(x, y, lat_i, lon_i)
            spatial = math.exp(-0.5 * (d_km / self.sigma) ** 2)
            lam += self.K * temporal * spatial

        return lam

    def predict_risk(self, lat, lon, time_days, recent_events, lookback_days=90):
        """
        Risk probability at (lat, lon, time_days).

        recent_events : list of (t_i, lat_i, lon_i)
        Returns risk_probability = 1 - exp(-intensity)
        """
        # Filter to lookback window
        cutoff = time_days - lookback_days
        history = [(t, la, lo) for t, la, lo in recent_events if cutoff <= t < time_days]
        lam = self.intensity(time_days, lat, lon, history)
        return 1.0 - math.exp(-lam)


# ---------------------------------------------------------------------------
# Blending function
# ---------------------------------------------------------------------------

def blend_risk(kde_score, hawkes_score, base_weight=0.7):
    """
    Combine long-term KDE density with short-term Hawkes excitation.

    Parameters
    ----------
    kde_score    : float 0-1 – spatial KDE density
    hawkes_score : float 0-1 – Hawkes risk probability
    base_weight  : float – weight for KDE (default 0.7)

    Returns
    -------
    float 0-1 – blended risk score
    """
    return base_weight * kde_score + (1 - base_weight) * hawkes_score


# ---------------------------------------------------------------------------
# Synthetic test
# ---------------------------------------------------------------------------

def generate_shinjuku_events(n=50, days=30, seed=42):
    """
    Generate synthetic clustered crime events around Shinjuku station.
    Uses a mix of background uniform events and clustered bursts.
    """
    rng = np.random.default_rng(seed)
    center_lat, center_lon = 35.6895, 139.6917

    events = []

    # --- Background events (60%) spread over the full period ---
    n_bg = int(n * 0.6)
    for _ in range(n_bg):
        t = rng.uniform(0, days)
        lat = center_lat + rng.normal(0, 0.005)
        lon = center_lon + rng.normal(0, 0.005)
        events.append((t, lat, lon))

    # --- Cluster 1: burst around day 25 (recent) ---
    n_c1 = int(n * 0.25)
    for _ in range(n_c1):
        t = 25 + rng.exponential(0.5)  # tight temporal cluster
        lat = center_lat + 0.002 + rng.normal(0, 0.001)
        lon = center_lon - 0.001 + rng.normal(0, 0.001)
        events.append((t, lat, lon))

    # --- Cluster 2: burst around day 10 (older) ---
    n_c2 = n - n_bg - n_c1
    for _ in range(n_c2):
        t = 10 + rng.exponential(0.5)
        lat = center_lat - 0.003 + rng.normal(0, 0.001)
        lon = center_lon + 0.003 + rng.normal(0, 0.001)
        events.append((t, lat, lon))

    events.sort(key=lambda e: e[0])
    return events


def main():
    print("=" * 60)
    print("  Spatio-Temporal Hawkes Process – Shinjuku Test")
    print("=" * 60)

    # Generate synthetic events
    events = generate_shinjuku_events(n=50, days=30)
    print(f"\nGenerated {len(events)} synthetic events over 30 days")
    print(f"  Time range: day {events[0][0]:.1f} – day {events[-1][0]:.1f}")

    # Show event distribution
    early = sum(1 for t, _, _ in events if t < 15)
    late = sum(1 for t, _, _ in events if t >= 20)
    print(f"  Events before day 15: {early}")
    print(f"  Events after  day 20: {late}  (recent cluster)")

    # Create model
    hawkes = SpatioTemporalHawkes(mu=0.05, K=0.3, omega=1/14, sigma=0.5)
    center_lat, center_lon = 35.6895, 139.6917

    # --- Test 1: Risk at different times ---
    print("\n--- Risk at Shinjuku center over time ---")
    print(f"{'Day':>6}  {'Intensity':>10}  {'Risk Prob':>10}")
    print("-" * 32)
    for day in [5, 10, 15, 20, 25, 26, 27, 28, 29, 30]:
        risk = hawkes.predict_risk(center_lat, center_lon, day, events)
        lam = hawkes.intensity(
            day, center_lat, center_lon,
            [(t, la, lo) for t, la, lo in events if t < day]
        )
        print(f"{day:>6}  {lam:>10.4f}  {risk:>10.4f}")

    # --- Test 2: Risk should be higher right after cluster ---
    print("\n--- Demonstrating self-excitation ---")
    # Right after the day-25 cluster vs. a quiet period (day 18)
    risk_quiet = hawkes.predict_risk(center_lat, center_lon, 18, events)
    risk_after_burst = hawkes.predict_risk(center_lat, center_lon, 26, events)
    risk_peak = hawkes.predict_risk(center_lat, center_lon, 27, events)

    print(f"  Risk at day 18 (quiet period):      {risk_quiet:.4f}")
    print(f"  Risk at day 26 (after burst start):  {risk_after_burst:.4f}")
    print(f"  Risk at day 27 (cluster peak):       {risk_peak:.4f}")
    print(f"  Ratio (peak / quiet):                {risk_peak / max(risk_quiet, 1e-9):.1f}x")

    # --- Test 3: Spatial decay ---
    print("\n--- Spatial decay from cluster center ---")
    print(f"{'Distance (km)':>14}  {'Risk':>8}")
    print("-" * 26)
    for offset_deg in [0, 0.005, 0.01, 0.02, 0.05, 0.1]:
        lat = center_lat + offset_deg
        risk = hawkes.predict_risk(lat, center_lon, 27, events)
        dist_km = offset_deg * 111.0  # approximate
        print(f"{dist_km:>14.2f}  {risk:>8.4f}")

    # --- Test 4: Blending ---
    print("\n--- Blended risk (KDE + Hawkes) ---")
    kde_scores = [0.8, 0.5, 0.2, 0.8, 0.1]
    hawkes_scores = [
        hawkes.predict_risk(center_lat, center_lon, 27, events),
        hawkes.predict_risk(center_lat, center_lon, 27, events),
        hawkes.predict_risk(center_lat, center_lon, 27, events),
        hawkes.predict_risk(center_lat, center_lon, 18, events),
        hawkes.predict_risk(center_lat, center_lon, 18, events),
    ]
    labels = [
        "High KDE + recent burst",
        "Med KDE + recent burst",
        "Low KDE + recent burst",
        "High KDE + quiet period",
        "Low KDE + quiet period",
    ]

    print(f"{'Scenario':<28} {'KDE':>6} {'Hawkes':>8} {'Blended':>8}")
    print("-" * 56)
    for label, kde_s, haw_s in zip(labels, kde_scores, hawkes_scores):
        blended = blend_risk(kde_s, haw_s)
        print(f"{label:<28} {kde_s:>6.2f} {haw_s:>8.4f} {blended:>8.4f}")

    print("\nDone.")


if __name__ == "__main__":
    main()
