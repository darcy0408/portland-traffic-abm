"""
Calibration check: our barrier physics vs ODOT's own attenuation numbers.

ODOT's Sound Barrier inventory carries, for most walls, the attenuation the
agency predicted when the wall was designed (atnatn_pre, e.g. "4-7 dBA") and
for some walls the attenuation actually measured after construction
(atnatn_msr). That is a free, per-wall ground truth for the PHYSICS layer
(not for the traffic model): if our Maekawa insertion loss lands in ODOT's
ranges and ranks walls the way ODOT's acousticians did, the barrier term can
be trusted inside the closure surface.

The geometry is deliberately the one a real measurement sees:
- The source is a LINE of traffic, not one perpendicular ray: point sources
  every 10 m along the snapped road for +-300 m, energy-summed. Oblique rays
  cross the wall with smaller path differences or miss its ends entirely, so
  a line source loses several dB against the single-ray textbook number.
  Skipping this is why naive Maekawa quotes (15+ dB) overshoot measured walls.
- Every wall in the inventory can shield every ray (corridors are recorded as
  chains of wall segments; an oblique ray missing this record's end often
  hits the next one).
- The receiver stands behind the wall midpoint on the shielded side (the ODOT
  point minus the road foot fixes the side), 1.5 m high, at first-row-house
  distances: 15, 30, and 60 m are all reported since the inventory does not
  say where ODOT measured.

Reads the step-1 parquet, runs no simulation. Outputs:
  data/processed/barrier_calibration.parquet   per-wall results
  outputs/figures/barrier_calibration.png      scatter + error histogram

Usage: python src/barrier_calibration.py
"""

import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from barrier_physics import (SOURCE_H_M, RECEIVER_H_M, barrier_band_il,
                             broadband_il_dba)
from noise import A_WEIGHTING_DB, per_vehicle_band_power

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALLS_PARQUET = os.path.join(BASE, "data", "processed", "odot_walls_lines.parquet")
OUT_PARQUET = os.path.join(BASE, "data", "processed", "barrier_calibration.parquet")
OUT_FIG = os.path.join(BASE, "outputs", "figures", "barrier_calibration.png")

LINE_HALF_M = 300.0    # the traffic line extends this far each way from the foot
LINE_STEP_M = 10.0     # point-source spacing along it
BEHIND_M = (15.0, 30.0, 60.0)   # candidate first-row receiver distances
NEAR_WALLS_M = 700.0   # only walls this close to a receiver can shield its rays

# assumed mean speed by snapped road class, km/h; sets the source spectrum only
SPEED_BY_CLASS = {"motorway": 100.0, "motorway_link": 100.0, "trunk": 100.0,
                  "trunk_link": 100.0, "primary": 70.0, "primary_link": 70.0}
SPEED_DEFAULT_KPH = 50.0


def parse_atnatn(s):
    """'4-7 dBA' -> (4.0, 7.0); '5 dBA' -> (5.0, 5.0); junk -> None."""
    nums = re.findall(r"\d+(?:\.\d+)?", str(s or ""))
    if not nums:
        return None
    lo = float(nums[0])
    hi = float(nums[1]) if len(nums) > 1 else lo
    return (lo, hi) if lo <= hi else (hi, lo)


def wall_speed(snap_class):
    return SPEED_BY_CLASS.get(str(snap_class).split(";")[0], SPEED_DEFAULT_KPH)


def line_source_levels(sources, rx, ry, walls_xy, walls_h, spec_w):
    """A-weighted energy at the receiver from the source line, with and
    without walls. spec_w is the normalized A-weighted band spectrum."""
    e_open = 0.0
    e_wall = 0.0
    for sx, sy in sources:
        d = float(np.hypot(rx - sx, ry - sy))
        if d < 1.0:
            d = 1.0
        # point source, spherical spreading; absolute offsets cancel in the
        # with/without difference so only relative terms matter
        g = 1.0 / (d * d)
        e_open += g
        il = barrier_band_il(sx, sy, rx, ry, walls_xy, walls_h,
                             sh=SOURCE_H_M, rh=RECEIVER_H_M)
        e_wall += g * float(np.sum(spec_w * 10.0 ** (-il / 10.0)))
    return e_open, e_wall


def main():
    walls = pd.read_parquet(WALLS_PARQUET)
    walls_xy = walls[["x0", "y0", "x1", "y1"]].to_numpy()
    walls_h = walls["ht_m"].to_numpy()
    mid = np.column_stack([(walls["x0"] + walls["x1"]) / 2.0,
                           (walls["y0"] + walls["y1"]) / 2.0])

    recs = []
    for i, w in walls.iterrows():
        mx, my = mid[i]
        # shielded-side direction: from the road foot toward the ODOT point
        nx, ny = mx - w["road_x"], my - w["road_y"]
        norm = float(np.hypot(nx, ny))
        if norm < 1.0:
            continue    # wall drawn on the road centerline, side unknowable
        nx, ny = nx / norm, ny / norm
        b = np.radians(w["bearing_deg"])
        tx, ty = np.cos(b), np.sin(b)
        offs = np.arange(-LINE_HALF_M, LINE_HALF_M + 1e-9, LINE_STEP_M)
        sources = np.column_stack([w["road_x"] + offs * tx,
                                   w["road_y"] + offs * ty])

        v = wall_speed(w["snap_class"])
        spec = per_vehicle_band_power(v) + A_WEIGHTING_DB
        spec_w = 10.0 ** (spec / 10.0)
        spec_w /= spec_w.sum()

        near = np.hypot(mid[:, 0] - mx, mid[:, 1] - my) < NEAR_WALLS_M
        nxy, nh = walls_xy[near], walls_h[near]

        row = {"objectid": w["objectid"], "hwy": w["hwy"], "ht_m": w["ht_m"],
               "len_m": w["len_m"], "wall_type": w["wall_type"],
               "snap_class": w["snap_class"], "snap_m": w["snap_m"],
               "v_kph": v}
        for d_behind in BEHIND_M:
            rx, ry = mx + nx * d_behind, my + ny * d_behind
            e_open, e_wall = line_source_levels(sources, rx, ry, nxy, nh, spec_w)
            row[f"il_{int(d_behind)}"] = 10.0 * np.log10(e_open / e_wall)
        # the textbook single perpendicular ray at 30 m, for the comparison story
        rx, ry = mx + nx * 30.0, my + ny * 30.0
        il_band = barrier_band_il(w["road_x"], w["road_y"], rx, ry, nxy, nh)
        row["il_perp_30"] = broadband_il_dba(il_band, v)
        for col in ("atnatn_pre", "atnatn_msr"):
            rng = parse_atnatn(w[col])
            row[f"{col}_lo"] = rng[0] if rng else np.nan
            row[f"{col}_hi"] = rng[1] if rng else np.nan
        recs.append(row)

    out = pd.DataFrame(recs)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    report(out)
    make_figure(out)


def _spearman(a, b):
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def report(out):
    print(f"{len(out)} walls calibrated")
    for c in ("il_15", "il_30", "il_60", "il_perp_30"):
        print(f"  {c}: median {out[c].median():.1f} dB(A), "
              f"IQR {out[c].quantile(0.25):.1f}-{out[c].quantile(0.75):.1f}")
    for col in ("atnatn_pre", "atnatn_msr"):
        lo, hi = out[f"{col}_lo"], out[f"{col}_hi"]
        has = lo.notna()
        m = out[has]
        mid_odot = (lo[has] + hi[has]) / 2.0
        print(f"\nvs {col} (n={int(has.sum())}, ODOT median midpoint "
              f"{mid_odot.median():.1f} dBA):")
        for c in ("il_15", "il_30", "il_60"):
            ours = m[c]
            inside = ((ours >= lo[has] - 1.0) & (ours <= hi[has] + 1.0)).mean()
            print(f"  {c}: median {ours.median():.1f}, "
                  f"bias {float((ours - mid_odot).median()):+.1f} dB, "
                  f"within range +-1 dB {100 * inside:.0f}%, "
                  f"Spearman vs midpoint {_spearman(ours, mid_odot):.2f}")


def make_figure(out):
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    ax = axes[0]
    for col, color, label in (("atnatn_pre", "tab:blue", "ODOT predicted"),
                              ("atnatn_msr", "tab:red", "ODOT measured")):
        lo, hi = out[f"{col}_lo"], out[f"{col}_hi"]
        has = lo.notna()
        mid_odot = ((lo + hi) / 2.0)[has]
        ax.errorbar(mid_odot, out.loc[has, "il_30"],
                    xerr=[(mid_odot - lo[has]), (hi[has] - mid_odot)],
                    fmt="o", ms=4, color=color, alpha=0.6, label=label,
                    elinewidth=0.8)
    lim = (0, 22)
    ax.plot(lim, lim, "k--", lw=0.8)
    ax.set_xlim(lim)
    ax.set_ylim(lim)
    ax.set_xlabel("ODOT attenuation, range midpoint (dBA)")
    ax.set_ylabel("our line-source insertion loss at 30 m (dB(A))")
    ax.set_title("Per-wall calibration against ODOT's own numbers")
    ax.legend()

    ax = axes[1]
    lo, hi = out["atnatn_pre_lo"], out["atnatn_pre_hi"]
    has = lo.notna()
    err = out.loc[has, "il_30"] - ((lo + hi) / 2.0)[has]
    ax.hist(err, bins=25, color="tab:blue", alpha=0.8)
    ax.axvline(0, color="k", lw=0.8)
    ax.axvline(err.median(), color="tab:red", lw=1.2,
               label=f"median {err.median():+.1f} dB")
    ax.set_xlabel("ours at 30 m minus ODOT predicted midpoint (dB)")
    ax.set_ylabel("walls")
    ax.set_title("Bias distribution")
    ax.legend()

    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_FIG), exist_ok=True)
    fig.savefig(OUT_FIG, dpi=150)
    print(f"\nwrote {OUT_FIG}")


if __name__ == "__main__":
    main()
