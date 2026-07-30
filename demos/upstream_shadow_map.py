"""UPSTREAM-SHADOW MAP for the Aug 14 SSRS Ignite talk, beat 15 (demo asset).

The claim on the slide: closing SE Powell casts a shadow UPSTREAM. Drivers
reroute long before they reach the blocked stretch, so feeder streets well away
from the zone lose traffic too, an effect the old 1.5 km corridor window could
not represent. The citable facts are ledger M20.18 (Jul 23): within 3 km of the
zone, SE McLoughlin Boulevard drops on 12 of 12 seeds (mean -113.5 g, -12%, on
an 885.9 g open baseline) and SE Foster Road drops on 12 of 12 (mean -81.0 g,
-90%). Grand Avenue and the Ross Island Bridge are NOT robust and are not
labeled here.

Read-only, no simulation: reads the 12 saved mixed-fleet metro closure sweep
pairs (sweepmix_powell_<seed>_{open,closed}_segments.parquet, the M20.17/M20.18
run family) plus the cached 20 km graph, and renders one PNG.

REPRODUCTION GATE (same pattern as the Section 6 forest figure builder): before
rendering, the script recomputes the per-street 12-seed statistics and checks
them against the ledger M20.18 values. If they do not reproduce, it aborts
without writing the figure, so the labels cannot drift from the ledger.

Usage:  python demos/upstream_shadow_map.py
Writes: outputs/figures/upstream_shadow_map.png
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Circle

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)
sys.path.append(os.path.join(_ROOT, "src"))

import config
import generate
from closure_robustness import name_of
from mixed_rerun import apply_metro_dirs

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]   # the fixed Jul 2 list
ZONE_M = 3000.0     # M20.18's scope: streets within 3 km of the zone center

# Ledger M20.18 values the recomputation must reproduce before anything renders.
# (mean delta g, mean %, all-12-seeds-down), tolerances one unit in the last
# quoted digit of the ledger entry.
GATE = {
    "Southeast McLoughlin Boulevard": (-113.5, -12.0),
    "Southeast Foster Road": (-81.0, -90.0),
}

# Deck dark-theme identity (matches animate_cars.py / the PU2 GIFs).
BG = "#0d1117"
STREET = "#39424e"
INK = "#e6edf3"
MUTED = "#9da7b3"


def load_deltas():
    """Per-segment mean NO2 delta (g) across the 12 sweep seeds, plus the
    per-street 3 km stats needed for the reproduction gate."""
    lat0, lon0, _ = config.CLOSURE
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    name_by_edge = {(u, v, k): name_of(d) for u, v, k, d in G.edges(keys=True, data=True)}
    ys = {n: float(G.nodes[n]["y"]) for n in G.nodes}
    xs = {n: float(G.nodes[n]["x"]) for n in G.nodes}

    acc = None
    per_seed_street = {}
    for seed in SEEDS:
        base = f"sweepmix_powell_{seed}"
        op = os.path.join(config.PROCESSED_DIR, f"{base}_open_segments.parquet")
        cp = os.path.join(config.PROCESSED_DIR, f"{base}_closed_segments.parquet")
        if not (os.path.exists(op) and os.path.exists(cp)):
            raise SystemExit(f"missing sweep pair for seed {seed}: {op}")
        o = pd.read_parquet(op)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "o"})
        c = pd.read_parquet(cp)[["u", "v", "key", "nox_g"]].rename(columns={"nox_g": "c"})
        df = o.merge(c, on=["u", "v", "key"], how="outer")
        df[["o", "c"]] = df[["o", "c"]].fillna(0.0)
        df["delta"] = config.F_NO2 * (df["c"] - df["o"])       # NO2 = F_NO2 * NOx
        df["open_no2"] = config.F_NO2 * df["o"]

        # accumulate the per-segment mean across seeds
        seg = df.set_index(["u", "v", "key"])[["delta", "open_no2"]]
        acc = seg if acc is None else acc.add(seg, fill_value=0.0)

        # per-street stats within 3 km, exactly feeder_robustness.py's recipe
        keys = list(zip(df["u"], df["v"], df["key"]))
        df["street"] = [name_by_edge.get(k, "") for k in keys]
        df["dist_m"] = [
            generate._haversine_m(lat0, lon0, 0.5 * (ys[u] + ys[v]), 0.5 * (xs[u] + xs[v]))
            for u, v, _k in keys
        ]
        near = df[(df["dist_m"] <= ZONE_M) & (df["street"] != "")]
        per_seed_street[seed] = near.groupby("street")[["open_no2", "delta"]].sum()
        print(f"  seed {seed} loaded")

    mean_seg = acc / len(SEEDS)
    return G, mean_seg, per_seed_street, (lat0, lon0)


def check_gate(per_seed_street):
    """Reproduce ledger M20.18 for the two labeled streets or abort."""
    n = len(per_seed_street)
    print(f"\nreproduction gate (M20.18, {n} seeds):")
    for street, (led_delta, led_pct) in GATE.items():
        d = np.array([per_seed_street[s]["delta"].get(street, 0.0) for s in SEEDS])
        o = np.array([per_seed_street[s]["open_no2"].get(street, 0.0) for s in SEEDS])
        n_down = int((d < 0).sum())
        mean_d = d.mean()
        mean_pct = float(np.mean(100.0 * d[o > 0] / o[o > 0]))
        ok = (n_down == n and abs(mean_d - led_delta) <= 1.0
              and abs(mean_pct - led_pct) <= 1.0)
        print(f"  {street}: mean {mean_d:+.1f} g ({mean_pct:+.0f}%), "
              f"{n_down}/{n} down  [ledger {led_delta:+.1f} g, {led_pct:+.0f}%]  "
              f"{'OK' if ok else 'MISMATCH'}")
        if not ok:
            raise SystemExit(
                f"GATE FAILED for {street}: recomputed {mean_d:+.1f} g / "
                f"{mean_pct:+.0f}% / {n_down}/{n} down vs ledger "
                f"{led_delta:+.1f} g / {led_pct:+.0f}% / 12/12. "
                "Figure NOT written; reconcile with RESULTS_LEDGER.md M20.18 first.")


def street_anchor(G, mean_seg, street_name, center, radius_m):
    """Where to point a label: the centroid of the street's segments within the
    3 km scope, weighted by |mean delta| so the label lands where the change is."""
    lat0, lon0 = center
    pts, wts = [], []
    for (u, v, k), row in mean_seg.iterrows():
        d = G.get_edge_data(u, v, k)
        if d is None or name_of(d) != street_name:
            continue
        my = 0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"]))
        mx = 0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"]))
        if generate._haversine_m(lat0, lon0, my, mx) > radius_m:
            continue
        pts.append((mx, my))
        wts.append(abs(row["delta"]) + 1e-9)
    pts, wts = np.array(pts), np.array(wts)
    w = wts / wts.sum()
    return float((pts[:, 0] * w).sum()), float((pts[:, 1] * w).sum())


def render(G, mean_seg, center, out_path):
    lat0, lon0 = center
    # window: the 3 km scope plus margin, so McLoughlin and Foster both fit
    half_m = 3400.0
    dlat = half_m / 111320.0
    dlon = half_m / (111320.0 * np.cos(np.radians(lat0)))
    bbox = (lon0 - dlon, lon0 + dlon, lat0 - dlat, lat0 + dlat)

    # geometry + color value per segment (only segments inside the window)
    segs_gray, segs_col, vals = [], [], []
    for (u, v, k), row in mean_seg.iterrows():
        d = G.get_edge_data(u, v, k)
        if d is None:
            continue
        xu, yu = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        xv, yv = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        if not (bbox[0] <= 0.5 * (xu + xv) <= bbox[1]
                and bbox[2] <= 0.5 * (yu + yv) <= bbox[3]):
            continue
        geom = d.get("geometry")
        coords = np.asarray(geom.coords) if geom is not None else np.array(
            [(xu, yu), (xv, yv)])
        if abs(row["delta"]) < 0.5:          # visually unchanged: base map only
            segs_gray.append(coords)
        else:
            segs_col.append(coords)
            vals.append(row["delta"])
    vals = np.array(vals)

    # background streets also need every in-window edge WITHOUT a delta row
    for u, v, k in G.edges(keys=True):
        if (u, v, k) in mean_seg.index:
            continue
        xu, yu = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        xv, yv = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        if bbox[0] <= 0.5 * (xu + xv) <= bbox[1] and bbox[2] <= 0.5 * (yu + yv) <= bbox[3]:
            d = G.get_edge_data(u, v, k)
            geom = d.get("geometry")
            segs_gray.append(np.asarray(geom.coords) if geom is not None
                             else np.array([(xu, yu), (xv, yv)]))

    # diverging color: blue = lost NO2, orange-red = gained, midpoint fades into
    # the dark background so unchanged streets disappear and movement pops
    cmap = LinearSegmentedColormap.from_list(
        "shadow", ["#4aa8ff", "#1d3a5c", BG, "#5c2a1d", "#ff6a3d"])
    # saturate at the 88th percentile of |delta|: the biggest movers (Holgate,
    # Powell near the zone) clip, which is fine, and the moderate movers
    # (Division, McLoughlin, Powell's long tail) stay visible instead of being
    # crushed into the dark midpoint
    vmax = float(np.percentile(np.abs(vals), 88))
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)

    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.add_collection(LineCollection(segs_gray, colors=STREET, linewidths=0.6))
    lc = LineCollection(segs_col, cmap=cmap, norm=norm, linewidths=2.0)
    lc.set_array(vals)
    ax.add_collection(lc)
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])
    ax.set_aspect(1.0 / np.cos(np.radians(lat0)))
    ax.axis("off")

    # the closure zone ring (red = closed, the closure-demo convention)
    _, _, zone_r = config.CLOSURE
    r_deg = zone_r / 111320.0
    ax.add_patch(Circle((lon0, lat0), r_deg * 3.0, fill=False,
                        edgecolor="#e8112d", linewidth=2.0, zorder=6))
    ax.annotate("SE Powell closed here\n(near zone −81% ± 5, 12-run mean)",
                xy=(lon0 + 0.011, lat0 - 0.0045), ha="center", va="top",
                color=INK, fontsize=11, zorder=7)

    # the two ledger-robust upstream feeders (M20.18); percentages paired with
    # gram deltas per the ledger's citation discipline
    for street, label, dxy in [
        ("Southeast McLoughlin Boulevard",
         "SE McLoughlin  −12% (−114 g)\nquieter on 12 of 12 runs", (-0.010, 0.004)),
        ("Southeast Foster Road",
         "SE Foster  −90% (−81 g)\nquieter on 12 of 12 runs", (0.008, -0.006)),
    ]:
        x, y = street_anchor(G, mean_seg, street, center, ZONE_M)
        ax.annotate(label, xy=(x, y), xytext=(x + dxy[0], y + dxy[1]),
                    color=INK, fontsize=11, ha="center", zorder=7,
                    arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))

    # context: the parallels that inherit the traffic (direction language only)
    for street, label, dxy in [
        ("Southeast Division Street", "SE Division (rises)", (0.012, 0.0022)),
        ("Southeast Holgate Boulevard", "SE Holgate (rises)", (0.004, -0.0040)),
    ]:
        x, y = street_anchor(G, mean_seg, street, center, ZONE_M)
        ax.annotate(label, xy=(x, y), xytext=(x + dxy[0], y + dxy[1]),
                    color=MUTED, fontsize=9.5, ha="center", zorder=7)

    ax.set_title("The closure's shadow reaches upstream",
                 color=INK, fontsize=16, pad=12)
    fig.text(0.5, 0.030,
             "mean change in modeled NO₂ across 12 runs  "
             "(blue = less, orange = more, dark = unchanged)   "
             "mixed fleet, metro network",
             color=MUTED, fontsize=9.5, ha="center")

    fig.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    print(f"\nwrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB)")


def main():
    apply_metro_dirs()
    G, mean_seg, per_seed_street, center = load_deltas()
    check_gate(per_seed_street)
    out = os.path.join(config.FIGURES_DIR, "upstream_shadow_map.png")
    render(G, mean_seg, center, out)


if __name__ == "__main__":
    main()
