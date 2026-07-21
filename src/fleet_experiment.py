"""Mixed-fleet experiment (originally exploratory; the mixed fleet was approved
as the live setting Jul 20 and config.FLEET_MIXED now defaults True).

Question: with every vehicle emitted as one all-diesel class (PC_D_EU4), which
fleet_preview.py predicted overstates network NOx roughly 4x, does switching
the LIVE simulation to the sourced Multnomah mixed fleet (config.FLEET_MIXED)
change the NO2 map's SHAPE, or only its SCALE? If only scale, the closure
DIFFERENCE result (the project's centerpiece) is insensitive to the fleet choice.
Answer (Jul 17 run): scale, not shape. All-diesel overstates NOx 3.76x; the
per-segment shape agreement is Spearman 0.926.

Two modes, kept in one file so the experiment is one self-contained recipe:

    python src/fleet_experiment.py run
        The ONE authoritative mixed-fleet simulation: identical configuration to
        the saved powell_through run (seed 42, 500 vehicles, 30% through-traffic,
        gravity demand) with FLEET_MIXED forced on and RUN_NAME
        "powell_through_mixedfleet". Refuses to run if the output already exists
        (one simulation only; a rerun would first need a deliberate delete).

    python src/fleet_experiment.py compare
        Read-only: loads the saved powell_through and powell_through_mixedfleet
        parquets and prints the comparison (totals ratio, per-segment shape
        agreement, ratio uniformity, and the fleet_preview offline prediction
        beside the realized number). Runs NO simulation. Reads NO count data:
        the held-out PBOT counts are never touched here.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

BASELINE_RUN = "powell_through"             # the saved all-diesel reference run
MIXED_RUN = "powell_through_mixedfleet"     # this experiment's one new run

# de-minimis: ratio statistics only on segments whose all-diesel NOx is at least
# this many grams, so near-zero segments (a handful of vehicle-steps) cannot
# swamp the spread with meaningless 0/0-ish ratios
DE_MINIMIS_NOX_G = 1.0


def _segments_path(run):
    return os.path.join(config.PROCESSED_DIR, f"{run}_segments.parquet")


def run_mixed():
    """The one mixed-fleet simulation. Same config as powell_through except the
    fleet flag and the run name, both overridden here (config.py on disk keeps
    FLEET_MIXED=False so the committed default behavior is unchanged)."""
    out = _segments_path(MIXED_RUN)
    if os.path.exists(out):
        raise SystemExit(f"{out} already exists. One simulation only: delete it "
                         "deliberately if you truly mean to rerun.")
    config.FLEET_MIXED = True
    config.RUN_NAME = MIXED_RUN

    import generate
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    print(f"Mixed-fleet run '{MIXED_RUN}': seed {config.RANDOM_SEED}, "
          f"{config.N_VEHICLES} vehicles, {config.N_STEPS} steps, "
          f"through-traffic {config.THROUGH_TRAFFIC_FRACTION:.0%}, "
          f"gravity demand {config.DEMAND_GRAVITY}")
    totals, nox, thru = generate.run_simulation(G)
    generate.save_results(totals, nox, thru)


def compare():
    """Compare the mixed-fleet surface against the saved all-diesel baseline."""
    d = pd.read_parquet(_segments_path(BASELINE_RUN))
    m = pd.read_parquet(_segments_path(MIXED_RUN))
    both = d.merge(m, on=["u", "v", "key"], suffixes=("_diesel", "_mixed"))
    assert len(both) == len(d) == len(m), "segment sets differ between runs"

    print(f"Mixed-fleet vs all-diesel on {len(both)} segments "
          f"({BASELINE_RUN} vs {MIXED_RUN}, same seed/demand/network)\n")

    # 1) traffic identity check: the fleet draw uses its own RNG stream, so the
    # traffic layer should be bit-identical; if it is not, the comparison would
    # confound fleet chemistry with changed traffic.
    same_val = np.allclose(both["value_diesel"], both["value_mixed"])
    same_thru = np.allclose(both["throughput_diesel"], both["throughput_mixed"])
    print(f"traffic identical between runs: activity {same_val}, "
          f"throughput {same_thru}")

    # 2) network totals and the headline scale ratio
    tot_d = both["nox_g_diesel"].sum()
    tot_m = both["nox_g_mixed"].sum()
    print(f"\nnetwork NOx: all-diesel {tot_d:.1f} g, mixed fleet {tot_m:.1f} g")
    print(f"scale ratio (all-diesel / mixed): {tot_d / tot_m:.2f}x  "
          f"(mixed = {tot_m / tot_d:.1%} of all-diesel)")
    f = config.F_NO2
    print(f"as NO2 (F_NO2={f}): {f * tot_d:.1f} g -> {f * tot_m:.1f} g")

    # 3) surface SHAPE agreement: does the mixed fleet reorder the map at all?
    active = both[(both["nox_g_diesel"] > 0) & (both["nox_g_mixed"] > 0)]
    rho = active["nox_g_diesel"].corr(active["nox_g_mixed"], method="spearman")
    pear = active["nox_g_diesel"].corr(active["nox_g_mixed"], method="pearson")
    print(f"\nper-segment NOx shape agreement ({len(active)} active segments): "
          f"Spearman {rho:.4f}, Pearson {pear:.4f}")

    # 4) how uniform is the per-segment mixed/diesel ratio? (uniform ratio =>
    # any DIFFERENCE map, like the closure, just rescales by one constant)
    sig = both[both["nox_g_diesel"] >= DE_MINIMIS_NOX_G].copy()
    sig["ratio"] = sig["nox_g_mixed"] / sig["nox_g_diesel"]
    share = sig["nox_g_diesel"].sum() / tot_d
    r = sig["ratio"]
    print(f"\nper-segment ratio (mixed/diesel) on {len(sig)} segments with "
          f">= {DE_MINIMIS_NOX_G} g diesel NOx ({share:.1%} of network NOx):")
    print(f"  min {r.min():.4f} | p5 {r.quantile(0.05):.4f} | "
          f"median {r.median():.4f} | p95 {r.quantile(0.95):.4f} | max {r.max():.4f}")
    print(f"  mean {r.mean():.4f}, std {r.std():.4f} "
          f"(coefficient of variation {r.std() / r.mean():.1%})")

    # 4b) the spread stratified by how much NOx a segment carries: quiet segments
    # see a handful of discrete vehicles, so WHICH classes happened to traverse
    # them dominates their ratio (one bus can triple a side street); busy segments
    # average over thousands of draws and converge. If the spread shrinks with
    # volume, the scatter is class-draw granularity, not a spatial restructuring.
    print("\nratio spread by segment size (mixed/diesel, NOx-weighted):")
    for thr in (1.0, 10.0, 50.0, 100.0):
        s = both[both["nox_g_diesel"] >= thr]
        rr, w = s["nox_g_mixed"] / s["nox_g_diesel"], s["nox_g_diesel"]
        wmean = np.average(rr, weights=w)
        wstd = float(np.sqrt(np.average((rr - wmean) ** 2, weights=w)))
        print(f"  >= {thr:5.0f} g: {len(s):4d} segments ({w.sum() / tot_d:5.1%} of "
              f"NOx)  weighted mean {wmean:.3f} +- {wstd:.3f} (CV {wstd / wmean:.1%})")

    # 4c) street level, the altitude the closure numbers live at (corridor sums
    # average over many segments and vehicles, so the class-draw noise cancels)
    from noise import load_network, _edge_length_and_name
    G = load_network()
    length, name = _edge_length_and_name(G)
    both["street"] = [name.get((row.u, row.v, row.key))
                      for row in both.itertuples()]
    st = (both.dropna(subset=["street"])
              .groupby("street")[["nox_g_diesel", "nox_g_mixed"]].sum())
    st["ratio"] = st["nox_g_mixed"] / st["nox_g_diesel"]
    top = st.sort_values("nox_g_diesel", ascending=False).head(12)
    print("\nstreet-level ratio, top 12 streets by NOx:")
    for street, row in top.iterrows():
        print(f"  {str(street)[:36]:<38} {row['ratio']:.3f}")
    tr = top["ratio"]
    print(f"  top-12 spread: min {tr.min():.3f} | max {tr.max():.3f} | "
          f"CV {tr.std() / tr.mean():.1%}")

    # 5) the offline fleet_preview prediction, recomputed on the same baseline so
    # realized vs predicted sit side by side (cruise-ratio reweight at each
    # segment's recovered mean speed; see fleet_preview.py for the approximation)
    import fleet_preview
    import fleet
    dd = d.copy()
    dd["length_m"] = [length.get((row.u, row.v, row.key), np.nan)
                      for row in dd.itertuples()]
    flowing = (dd["throughput"] > 0) & (dd["value"] > 0)
    v_mean = np.full(len(dd), np.nan)
    v_mean[flowing.to_numpy()] = (dd.loc[flowing, "length_m"]
                                  * dd.loc[flowing, "throughput"]
                                  / dd.loc[flowing, "value"]).to_numpy()
    mix = fleet.resolved(fleet.PORTLAND_FLEET)
    ratio_prev = np.array([fleet_preview.fleet_diesel_ratio(vi, mix)
                           if np.isfinite(vi) else np.nan for vi in v_mean])
    valid = np.isfinite(ratio_prev)
    nox_prev = float((dd["nox_g"].to_numpy()[valid] * ratio_prev[valid]).sum())
    nox_base = float(dd["nox_g"].to_numpy()[valid].sum())
    print(f"\nfleet_preview offline prediction (cruise-ratio reweight): "
          f"mixed = {nox_prev / nox_base:.1%} of all-diesel "
          f"(overstatement ~{nox_base / nox_prev:.2f}x)")
    print(f"realized in the live run:                                "
          f"mixed = {tot_m / tot_d:.1%} of all-diesel "
          f"(overstatement {tot_d / tot_m:.2f}x)")

    # how much of the per-segment ratio variation the preview's speed-only model
    # explains (the systematic congestion part) vs per-vehicle class-draw noise
    both["pred_ratio"] = ratio_prev
    s = both[both["nox_g_diesel"] >= 10.0].copy()
    s["ratio"] = s["nox_g_mixed"] / s["nox_g_diesel"]
    print(f"\non segments >= 10 g: corr(realized ratio, speed-predicted ratio) "
          f"Pearson {s['ratio'].corr(s['pred_ratio']):.3f}, Spearman "
          f"{s['ratio'].corr(s['pred_ratio'], method='spearman'):.3f}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "run":
        run_mixed()
    elif mode == "compare":
        compare()
    else:
        raise SystemExit("usage: python src/fleet_experiment.py {run|compare}")
