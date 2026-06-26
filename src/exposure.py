"""Residential NO2 exposure change from a road closure (analysis only).

This script answers a question the closure experiment sets up but does not yet
quantify: when a street is closed and traffic reroutes, how does the change in
modeled NO2 land on the people who live nearby? It reads the already-computed
open and closed segment surfaces, the block-group population around the study
area, and the cached street graph, and assigns each block group a local NO2
exposure (the NO2 on all street segments near its centroid). It then compares
open vs closed.

Important honesty note: the NO2 here is MODELED output from the agent simulation,
not measured air quality. The HBEFA NOx emissions and the F_NO2 fraction are
literature values, not Portland sensor calibrations. So every number below is a
relative, modeled comparison (open scenario vs closed scenario under the same
model), not a claim about absolute pollution anyone breathes. Read the percent
changes and the who-goes-up-vs-down split, not the raw microgram-like totals.

This script runs NO simulation and writes only its own outputs: it reads the
input parquet files and the graph, prints a summary, and saves one figure. It
never touches the data files generate.py produces.

Run:  python src/exposure.py
"""
import os
import sys

import numpy as np
import pandas as pd

# Same path setup the other src scripts use, so `import config` and the shared
# predictor helpers resolve whether this is run from the repo root or src/.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import predictors  # reuse _segment_midpoints, _local_xy, load_network (do not edit it)

import matplotlib
matplotlib.use("Agg")  # non-interactive backend: render straight to a file, no display
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm


# Default input surfaces produced by the closure experiment (python src/generate.py closure).
OPEN_PATH = os.path.join(config.PROCESSED_DIR, "powell_no2_open_segments.parquet")
CLOSED_PATH = os.path.join(config.PROCESSED_DIR, "powell_no2_closed_segments.parquet")
# Default exposure buffer radius. Each block group "breathes" the NO2 on segments
# whose midpoint sits within this many meters of its centroid. 400 m is one of
# Rao's buffer radii (config.BUFFER_RADII_M) and is a reasonable local-walk scale.
DEFAULT_RADIUS_M = 400.0


def _segment_no2(G, df):
    """Return per-segment modeled NO2 plus each segment's midpoint (lat, lon).

    NO2 on a segment is F_NO2 times the accumulated NOx grams, the same relation
    visualize.py uses, kept out of the sim so the fraction can be retuned without
    a rerun. Midpoints come from the shared predictors helper so the distance math
    matches the rest of the pipeline exactly.
    """
    lat, lon = predictors._segment_midpoints(G, df)          # aligned row-for-row with df
    no2 = config.F_NO2 * df["nox_g"].to_numpy(dtype=float)   # modeled NO2 per segment
    return no2, lat, lon


def _exposure_by_bg(bg, seg_no2, seg_lat, seg_lon, radius_m):
    """Local modeled NO2 exposure for each block group.

    For one block group, the exposure is the sum of segment NO2 over every segment
    whose midpoint lies within radius_m of the block-group centroid. We do the
    distance test in local meters (predictors._local_xy), the same flat-earth
    projection the predictor buffers use; at these radii its error is well under a
    meter. Returns an array aligned to bg's rows.
    """
    # Project both the block-group centroids and the segment midpoints into the
    # same local meter grid, then test membership circle by circle.
    bg_x, bg_y = predictors._local_xy(bg["lat"].to_numpy(float), bg["lon"].to_numpy(float))
    seg_x, seg_y = predictors._local_xy(np.asarray(seg_lat), np.asarray(seg_lon))
    r2 = float(radius_m) ** 2

    exposure = np.empty(len(bg))
    for i in range(len(bg)):
        dx = seg_x - bg_x[i]
        dy = seg_y - bg_y[i]
        within = (dx * dx + dy * dy) <= r2   # segments inside this block group's buffer
        exposure[i] = seg_no2[within].sum()  # total modeled NO2 they contribute
    return exposure


def compute_exposure_change(open_path=OPEN_PATH, closed_path=CLOSED_PATH,
                            radius_m=DEFAULT_RADIUS_M):
    """Build the per-block-group open/closed exposure table and the summary stats.

    Parameterized by the two surface paths and the buffer radius so the same
    analysis can be pointed at any other open/closed scenario pair later. Returns
    (bg_table, summary_dict). The table has one row per block group with its
    population, open and closed exposure, and the absolute and percent change.
    """
    # Load the two modeled surfaces and the resident block groups. All reads, no writes.
    open_df = pd.read_parquet(open_path)
    closed_df = pd.read_parquet(closed_path)
    bg = pd.read_parquet(os.path.join(config.PROCESSED_DIR, "landuse_bg.parquet")).copy()

    # The graph carries the segment geometry (node coordinates); the parquet does not.
    G = predictors.load_network()

    # Per-segment modeled NO2 and midpoints for each scenario. The closed surface has
    # fewer segments (the closed ones are removed before routing), so each scenario is
    # handled with its own segment set and its own midpoints.
    open_no2, open_lat, open_lon = _segment_no2(G, open_df)
    closed_no2, closed_lat, closed_lon = _segment_no2(G, closed_df)

    # Local exposure per block group, open vs closed.
    bg["exposure_open"] = _exposure_by_bg(bg, open_no2, open_lat, open_lon, radius_m)
    bg["exposure_closed"] = _exposure_by_bg(bg, closed_no2, closed_lat, closed_lon, radius_m)

    # Absolute and relative change. pct_change guards against a divide-by-zero for any
    # block group whose buffer caught no traffic in the open case.
    bg["change_abs"] = bg["exposure_closed"] - bg["exposure_open"]
    with np.errstate(divide="ignore", invalid="ignore"):
        bg["change_pct"] = np.where(
            bg["exposure_open"] > 0,
            100.0 * bg["change_abs"] / bg["exposure_open"],
            np.nan,
        )

    # Population-weighted mean exposure: each block group counts in proportion to how
    # many people live in it, so a busy-but-empty block group does not dominate the
    # headline number. This is the per-resident average modeled exposure.
    pop = bg["population"].to_numpy(float)
    pop_total = pop.sum()
    pw_open = float((pop * bg["exposure_open"].to_numpy()).sum() / pop_total)
    pw_closed = float((pop * bg["exposure_closed"].to_numpy()).sum() / pop_total)
    pw_pct = 100.0 * (pw_closed - pw_open) / pw_open if pw_open > 0 else float("nan")

    # Residents living where local modeled NO2 rises, falls, or is unchanged under the
    # closure. A tiny tolerance keeps floating-point noise from registering as a change.
    tol = 1e-9
    rises = bg["change_abs"] > tol
    falls = bg["change_abs"] < -tol
    same = ~(rises | falls)

    summary = {
        "radius_m": float(radius_m),
        "n_bg": int(len(bg)),
        "pop_total": float(pop_total),
        "pw_open": pw_open,
        "pw_closed": pw_closed,
        "pw_pct": pw_pct,
        "pop_up": float(pop[rises.to_numpy()].sum()),
        "pop_down": float(pop[falls.to_numpy()].sum()),
        "pop_same": float(pop[same.to_numpy()].sum()),
    }
    return bg, summary


def print_summary(bg, summary, top_n=5):
    """Print the exposure-change summary in plain language."""
    print("=" * 70)
    print("Residential NO2 exposure change from the road closure (MODELED)")
    print("=" * 70)
    print(f"Buffer radius: {summary['radius_m']:.0f} m   "
          f"Block groups: {summary['n_bg']}   "
          f"Residents: {summary['pop_total']:.0f}")
    print()
    print("NOTE: NO2 here is modeled simulation output (F_NO2 * HBEFA NOx), not")
    print("measured air quality. Read these as relative open-vs-closed changes.")
    print()
    print("Population-weighted mean local NO2 exposure (per-resident average):")
    print(f"  open   : {summary['pw_open']:.3f}")
    print(f"  closed : {summary['pw_closed']:.3f}")
    print(f"  change : {summary['pw_pct']:+.2f}%")
    print()
    print("Residents by direction of change in their local modeled NO2:")
    print(f"  exposure rises    : {summary['pop_up']:.0f}")
    print(f"  exposure falls    : {summary['pop_down']:.0f}")
    print(f"  unchanged         : {summary['pop_same']:.0f}")
    print()

    # Largest increases and decreases by percent change (ignoring block groups with
    # no open-case baseline, whose pct is undefined).
    ranked = bg.dropna(subset=["change_pct"]).sort_values("change_pct")
    cols = ["bg_geoid", "population", "exposure_open", "exposure_closed", "change_pct"]

    print(f"Largest exposure INCREASES (top {top_n}):")
    for _, r in ranked.tail(top_n).iloc[::-1].iterrows():
        print(f"  {int(r['bg_geoid'])}  pop={int(r['population']):5d}  "
              f"open={r['exposure_open']:.3f} -> closed={r['exposure_closed']:.3f}  "
              f"{r['change_pct']:+.1f}%")
    print()
    print(f"Largest exposure DECREASES (top {top_n}):")
    for _, r in ranked.head(top_n).iterrows():
        print(f"  {int(r['bg_geoid'])}  pop={int(r['population']):5d}  "
              f"open={r['exposure_open']:.3f} -> closed={r['exposure_closed']:.3f}  "
              f"{r['change_pct']:+.1f}%")
    print("=" * 70)


def make_figure(bg, summary, out_path):
    """Map of block-group centroids: size = population, color = exposure change.

    Presentation-quality: white background, faint street network for context, a
    diverging red/blue scale centered at zero (red = modeled NO2 goes up under the
    closure, blue = down), a colorbar, a title, and a one-line modeled-not-measured
    caption.
    """
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 9), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Faint street network for spatial context. Drawn light grey so the block-group
    # markers read on top. Pulled from the cached graph's edge geometry.
    try:
        import osmnx as ox
        G = predictors.load_network()
        edges = ox.graph_to_gdfs(G, nodes=False)
        edges.plot(ax=ax, linewidth=0.4, color="0.82", zorder=1)
    except Exception:
        # The network is decoration only; if it cannot be drawn the markers still stand.
        pass

    # Diverging color scale centered on zero change so red and blue are symmetric and
    # zero is white. The range is the largest absolute change, so the extremes are
    # saturated and small changes stay pale.
    change = bg["change_abs"].to_numpy(float)
    vmax = float(np.nanmax(np.abs(change))) or 1.0
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

    # Marker area scales with population so big neighborhoods read as bigger dots.
    pop = bg["population"].to_numpy(float)
    sizes = 60.0 + 900.0 * (pop / pop.max())

    sc = ax.scatter(
        bg["lon"], bg["lat"],
        c=change, cmap="RdBu_r", norm=norm,
        s=sizes, edgecolors="0.25", linewidths=0.8, zorder=3,
    )

    # Mark the closure zone center so viewers can tie the pattern to the closed block.
    clat, clon, crad = config.CLOSURE
    ax.scatter([clon], [clat], marker="x", c="black", s=120, linewidths=2.0,
               zorder=4, label="closure zone")
    ax.legend(loc="upper right", frameon=True, fontsize=9)

    cbar = fig.colorbar(sc, ax=ax, shrink=0.8, pad=0.02)
    cbar.set_label("Change in local modeled NO2  (closed - open)\n"
                   "red = rises, blue = falls", fontsize=10)

    ax.set_title(
        f"Road closure shifts modeled residential NO2 exposure\n"
        f"19 block groups, {summary['radius_m']:.0f} m buffer  |  "
        f"per-resident mean {summary['pw_pct']:+.1f}%  |  "
        f"{summary['pop_up']:.0f} residents up, {summary['pop_down']:.0f} down",
        fontsize=12, pad=12,
    )
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.set_aspect("equal", adjustable="datalim")  # keep the map from stretching

    # One-line honesty caption under the axes.
    fig.text(0.5, 0.015,
             "Marker size = block-group population. NO2 is modeled agent-simulation "
             "output (relative comparison), not measured air quality.",
             ha="center", fontsize=8.5, color="0.35")

    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(out_path, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return out_path


def main():
    bg, summary = compute_exposure_change()
    print_summary(bg, summary)
    out_path = os.path.join(config.BASE_DIR, "outputs", "demo", "6_exposure_change.png")
    saved = make_figure(bg, summary, out_path)
    print(f"\nFigure saved to {saved}")


if __name__ == "__main__":
    main()
