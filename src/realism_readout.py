"""ANALYSIS-ONLY readout: the Phase 2 (driver heterogeneity) and Phase 3 (MOBIL
lane changing) payoff numbers from the four sequential corridor runs written by
src/realism_runs.py.

This script NEVER runs the simulation. Per CLAUDE.md's architecture rule, data
generation and analysis are separate: generate.py (and realism_runs.py, which
drives it) write parquet files, and everything downstream only reads them. If
one of the four run files is missing, this script raises rather than running
the sim to produce it.

It reads:
    data/processed/realism_base_segments.parquet
    data/processed/realism_drivers_segments.parquet
    data/processed/realism_mobil_segments.parquet
    data/processed/realism_both_segments.parquet
    data/network/graph.graphml                        (cached corridor graph)

and prints a tidy sectioned report, no plotting (visualization is a separate
script by project convention) and no writes to data/.

Report sections:
  1. Per-run headline table (speed, throughput, activity, segment-level spread)
  2. Phase 2 payoff: does driver heterogeneity's speed variance move the
     CNOSSOS noise surface? (base vs drivers, mean-speed-only noise vs a
     speed-distribution-aware quadrature)
  3. Phase 3 payoff: what does MOBIL lane changing do to segment throughput?
     (mobil vs base, overall and split multi-lane vs single-lane)
  4. Interaction: does realism_both equal the additive prediction from the two
     single-flag deltas? First-ever measurement of the two flags interacting.
  5. Caveats

Run it:  python src/realism_readout.py
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import noise                      # CNOSSOS functions reused, not reimplemented
from generate import _parse_lanes  # the one lane-parsing rule, mirrored exactly


RUN_NAMES = ["realism_base", "realism_drivers", "realism_mobil", "realism_both"]


# --- loading ------------------------------------------------------------
def load_run(run_name):
    """Load one run's saved per-segment parquet. Reuses noise.py's loader with
    an explicit run_name (never config.RUN_NAME, so this never depends on
    whatever the config module currently has set). Raises loudly, rather than
    simulating, if the file is not already on disk."""
    return noise.load_run_segments(run_name)


def add_speed_moments(df):
    """Attach mean_speed_mps, var_mps2 and sd_mps to a run's DataFrame from its
    v_sum / v2_sum time-weighted speed accumulators (see generate.save_results
    docstring): mean = v_sum/value, variance = v2_sum/value - mean^2.

    Guarded: only segments with value > 0 (any recorded activity) get a mean;
    everything else is NaN, not a divide-by-zero warning. Variance from finite
    floating-point sums can come out as a tiny negative number even though a
    true variance cannot be negative (cancellation in v2_sum/value - mean^2);
    that is clamped to 0 before the sqrt so sd is never NaN from that alone.
    """
    df = df.copy()
    n = len(df)
    mean = np.full(n, np.nan)
    var = np.full(n, np.nan)
    flowing = (df["value"] > 0).to_numpy()

    v = df.loc[flowing, "value"].to_numpy()
    vs = df.loc[flowing, "v_sum"].to_numpy()
    v2s = df.loc[flowing, "v2_sum"].to_numpy()
    m = vs / v
    raw_var = v2s / v - m ** 2
    clamped_var = np.clip(raw_var, 0.0, None)   # float-roundoff negatives -> 0

    mean[flowing] = m
    var[flowing] = clamped_var

    df["mean_speed_mps"] = mean
    df["var_mps2"] = var
    df["sd_mps"] = np.sqrt(var)   # NaN stays NaN (sqrt of NaN is NaN, not an error)
    return df


def pct(x, q):
    """Percentile of a 1-D array-like with NaNs dropped, or NaN if nothing left."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float("nan")


# --- section 1: headline table -------------------------------------------
def headline_row(run_name, df):
    """One run's summary numbers for the headline table."""
    total_value = df["value"].sum()
    total_v_sum = df["v_sum"].sum()
    # network mean speed = total distance-weighted... here it's a TIME-weighted
    # average over the whole run: sum(v_sum) / sum(value), guarded against an
    # all-silent network (should not happen with real runs, but never trust it).
    net_speed_mps = total_v_sum / total_value if total_value > 0 else float("nan")

    flowing = df["value"] > 0
    sd = df.loc[flowing, "sd_mps"]
    return {
        "run": run_name,
        "net_mean_speed_kph": net_speed_mps * 3.6,
        "total_throughput": df["throughput"].sum(),
        "total_veh_seconds": total_value,
        "n_flowing_segments": int(flowing.sum()),
        "median_sd_kph": pct(sd, 50) * 3.6,
        "p90_sd_kph": pct(sd, 90) * 3.6,
    }


def print_headline_table(runs):
    print("\n" + "=" * 78)
    print("1. PER-RUN HEADLINE TABLE")
    print("=" * 78)
    rows = [headline_row(name, df) for name, df in runs.items()]
    header = (f"{'run':<18}{'mean kph':>10}{'throughput':>12}{'veh-sec':>12}"
              f"{'flowing':>9}{'med SD kph':>12}{'p90 SD kph':>12}")
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['run']:<18}{r['net_mean_speed_kph']:>10.2f}"
              f"{r['total_throughput']:>12,.0f}{r['total_veh_seconds']:>12,.0f}"
              f"{r['n_flowing_segments']:>9d}{r['median_sd_kph']:>12.3f}"
              f"{r['p90_sd_kph']:>12.3f}")
    print("(mean/SD in km/h; throughput = total vehicles that fully crossed a "
          "segment in the hour; veh-sec = total vehicle-seconds of activity)")


# --- section 2: Phase 2 payoff (noise sensitivity to speed spread) --------
def noise_two_ways(df):
    """Per-segment CNOSSOS level two ways, on flowing segments only (throughput
    > 0, value > 0, mean speed > 0):

      (a) mean-speed-only: exactly src/noise.py's build_noise_surface -- one
          CNOSSOS evaluation at the segment's mean speed.
      (b) speed-distribution-aware: a 3-point Gauss-Hermite quadrature over
          N(mean, sd), i.e. we treat the two accumulated moments (mean, sd)
          from v_sum/v2_sum AS IF the within-segment speed distribution were
          Gaussian. That is an approximation -- the two moments do not prove
          Gaussianity -- but it is the honest first reading those two moments
          allow without saving every vehicle's instantaneous speed. Flow Q
          (throughput) is held FIXED across the three quadrature nodes; only
          the speed varies. Nodes are speeds mean +/- sqrt(3)*sd and mean,
          weights 1/6, 2/3, 1/6 (the standard 3-point Gauss-Hermite rule for a
          Gaussian integrand). Each node's level is computed with the SAME
          CNOSSOS functions as (a); the three levels are then ENERGY-averaged
          (sum of 10^(L/10), weighted, then 10*log10) because sound levels add
          in the linear (power) domain, not the dB domain.

    Returns a DataFrame indexed like df, columns level_a, level_b, delta
    (b - a), restricted to flowing segments.
    """
    flowing = (df["throughput"] > 0) & (df["value"] > 0) & (df["mean_speed_mps"] > 0)
    sub = df.loc[flowing, ["u", "v", "key", "throughput", "mean_speed_mps", "sd_mps"]].copy()

    q = sub["throughput"].to_numpy()
    mean_kph = sub["mean_speed_mps"].to_numpy() * 3.6
    sd_kph = sub["sd_mps"].to_numpy() * 3.6

    level_a = np.full(len(sub), np.nan)
    level_b = np.full(len(sub), np.nan)

    sqrt3 = np.sqrt(3.0)
    for i in range(len(sub)):
        qi, mi, si = q[i], mean_kph[i], sd_kph[i]

        # (a) single evaluation at the mean speed -- src/noise.py's own method
        lwa_a = noise.segment_line_power_dba(qi, mi)
        level_a[i] = noise.propagate_line(lwa_a) if lwa_a is not None else np.nan

        # (b) 3-point Gauss-Hermite quadrature, speeds clamped >= 1 km/h so a
        # low-mean/high-sd segment never asks CNOSSOS for a zero or negative
        # speed. Q is fixed at qi for every node (only speed is distributed).
        nodes_kph = np.clip([mi - sqrt3 * si, mi, mi + sqrt3 * si], 1.0, None)
        weights = np.array([1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0])
        levels = np.array([
            noise.propagate_line(noise.segment_line_power_dba(qi, v))
            for v in nodes_kph
        ])
        # energy (power-domain) average, then back to dB
        level_b[i] = 10.0 * np.log10(np.sum(weights * 10.0 ** (levels / 10.0)))

    sub["level_a_dba"] = level_a
    sub["level_b_dba"] = level_b
    sub["delta_dba"] = level_b - level_a
    return sub


def summarize_delta(sub, label):
    d = sub["delta_dba"].to_numpy()
    d = d[np.isfinite(d)]
    print(f"\n  {label}: n={len(d)} flowing segments")
    if len(d) == 0:
        print("    no flowing segments -- nothing to summarize")
        return
    print(f"    delta (quadrature - mean-only), dB(A): "
          f"median {np.median(d):+.4f}  mean {np.mean(d):+.4f}  "
          f"p5 {pct(d, 5):+.4f}  p95 {pct(d, 95):+.4f}  max|delta| {np.max(np.abs(d)):.4f}")
    print(f"    segments with |delta| >= 0.1 dB: {int(np.sum(np.abs(d) >= 0.1))}   "
          f">= 0.5 dB: {int(np.sum(np.abs(d) >= 0.5))}")


def phase2_report(runs, length, name):
    print("\n" + "=" * 78)
    print("2. PHASE 2 PAYOFF -- driver heterogeneity's effect on the noise surface")
    print("=" * 78)
    print("Does the speed VARIANCE driver heterogeneity adds move the CNOSSOS noise")
    print("surface, beyond what evaluating at the mean speed alone would show?")

    base_sub = noise_two_ways(runs["realism_base"])
    drv_sub = noise_two_ways(runs["realism_drivers"])

    summarize_delta(base_sub, "realism_base  (signal/queue-induced spread only)")
    summarize_delta(drv_sub, "realism_drivers (+ driver heterogeneity)")

    # the KEY comparison: heterogeneity's ADDED effect, not the raw drivers
    # number. The base run already has nonzero speed spread from signals and
    # queues even with identical drivers, so Phase 2's claim has to be about
    # the DELTA versus base, not the absolute spread.
    base_flowing = runs["realism_base"]
    drv_flowing = runs["realism_drivers"]
    base_sd = base_flowing.loc[base_flowing["value"] > 0, "sd_mps"] * 3.6
    drv_sd = drv_flowing.loc[drv_flowing["value"] > 0, "sd_mps"] * 3.6
    print(f"\n  Median per-segment speed SD (km/h): base {pct(base_sd, 50):.3f} "
          f"vs drivers {pct(drv_sd, 50):.3f}  "
          f"(+{pct(drv_sd, 50) - pct(base_sd, 50):.3f} km/h from heterogeneity)")

    d_base = base_sub["delta_dba"].to_numpy()
    d_base = d_base[np.isfinite(d_base)]
    d_drv = drv_sub["delta_dba"].to_numpy()
    d_drv = d_drv[np.isfinite(d_drv)]
    print(f"  Median |noise delta| (dB(A)): base {np.median(np.abs(d_base)):.4f} "
          f"vs drivers {np.median(np.abs(d_drv)):.4f}  "
          f"(+{np.median(np.abs(d_drv)) - np.median(np.abs(d_base)):.4f} dB(A) "
          f"from heterogeneity, on top of the base run's own spread)")

    # top 5 segments by |delta| in the drivers run, with street names
    top5 = drv_sub.reindex(drv_sub["delta_dba"].abs().sort_values(ascending=False).index).head(5)
    print("\n  Top 5 segments by |noise delta| in realism_drivers:")
    print(f"    {'street':<28}{'u':>12}{'v':>12}{'k':>3}{'mean kph':>10}"
          f"{'sd kph':>8}{'delta dB':>10}")
    for r in top5.itertuples():
        nm = name.get((r.u, r.v, r.key)) or "(unnamed)"
        nm = nm if len(nm) <= 27 else nm[:24] + "..."
        drv_row = runs["realism_drivers"]
        row = drv_row[(drv_row["u"] == r.u) & (drv_row["v"] == r.v) & (drv_row["key"] == r.key)].iloc[0]
        print(f"    {nm:<28}{r.u:>12}{r.v:>12}{r.key:>3}"
              f"{row['mean_speed_mps'] * 3.6:>10.2f}{row['sd_mps'] * 3.6:>8.2f}"
              f"{r.delta_dba:>+10.4f}")


# --- section 3: Phase 3 payoff (MOBIL lane changing vs throughput) --------
def edge_lane_counts(G):
    """Per-edge (u, v, key) -> lane count, using generate._parse_lanes -- the
    SAME rule build_mobil_context applies when generate.py actually runs a
    MOBIL simulation (min of merged-edge tag values, halved unless one-way,
    clamped to [1, config.LANES_MAX]).

    _parse_lanes only bothers reading the OSM 'lanes' tag when config.LANES_
    ENABLED or config.MOBIL_ENABLED is True (see generate.py); with both off it
    short-circuits to 1 for every edge. This script runs no simulation, but it
    still needs the REAL per-edge lane count to classify segments as multi- vs
    single-lane, so MOBIL_ENABLED is flipped on for the duration of this one
    pure per-edge tag parse (no vehicles, no stepping, nothing simulated) and
    restored immediately after."""
    prior = config.MOBIL_ENABLED
    config.MOBIL_ENABLED = True
    try:
        lanes = {(u, v, k): _parse_lanes(d) for u, v, k, d in G.edges(keys=True, data=True)}
    finally:
        config.MOBIL_ENABLED = prior
    return lanes


def safe_corr(x, y):
    """Pearson and Spearman correlation, guarded: scipy raises/produces NaN when
    an input is constant (zero variance), which a small subset can easily be
    (e.g. every single-lane segment's throughput might tie). Return NaN pairs
    with a note rather than letting an exception or a silent NaN through."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    pear = stats.pearsonr(x, y)[0]
    spear = stats.spearmanr(x, y)[0]
    return float(pear), float(spear)


def phase3_report(runs, length, name, lanes):
    print("\n" + "=" * 78)
    print("3. PHASE 3 PAYOFF -- MOBIL lane changing's effect on segment throughput")
    print("=" * 78)

    base = runs["realism_base"][["u", "v", "key", "throughput"]].rename(
        columns={"throughput": "throughput_base"})
    mob = runs["realism_mobil"][["u", "v", "key", "throughput"]].rename(
        columns={"throughput": "throughput_mobil"})
    joined = base.merge(mob, on=["u", "v", "key"], how="outer")
    n_mismatch = joined["throughput_base"].isna().sum() + joined["throughput_mobil"].isna().sum()
    if n_mismatch:
        print(f"  WARNING: {n_mismatch} segment(s) did not join on (u, v, key) "
              f"between realism_base and realism_mobil -- unexpected, since both "
              f"runs share the same cached graph.")
    joined = joined.dropna(subset=["throughput_base", "throughput_mobil"])
    joined["delta"] = joined["throughput_mobil"] - joined["throughput_base"]
    joined["lanes"] = [lanes.get((r.u, r.v, r.key), 1) for r in joined.itertuples()]
    joined["multi_lane"] = joined["lanes"] > 1

    tb, tm = joined["throughput_base"].sum(), joined["throughput_mobil"].sum()
    print(f"  Total throughput: base {tb:,.0f}  mobil {tm:,.0f}  "
          f"({'+' if tm >= tb else ''}{tm - tb:,.0f}, "
          f"{100 * (tm - tb) / tb if tb else float('nan'):+.2f}%)")

    pear, spear = safe_corr(joined["throughput_base"], joined["throughput_mobil"])
    print(f"  Per-segment throughput correlation (base vs mobil, all "
          f"{len(joined)} segments): Pearson r={pear:.4f}  Spearman rho={spear:.4f}")
    print(f"  Mean |per-segment throughput change|: {joined['delta'].abs().mean():.3f} veh/hr")

    n_multi = int(joined["multi_lane"].sum())
    n_single = len(joined) - n_multi
    print(f"\n  MOBIL can only ACT on multi-lane segments: {n_multi} of {len(joined)} "
          f"segments have >1 lane by the OSM tag parse above (config.LANES_MAX="
          f"{config.LANES_MAX} clamp); the other {n_single} are single-file and MOBIL "
          f"has no second lane to change into.")

    for label, mask in (("multi-lane", joined["multi_lane"]),
                        ("single-lane", ~joined["multi_lane"])):
        g = joined.loc[mask]
        tb_g, tm_g = g["throughput_base"].sum(), g["throughput_mobil"].sum()
        pear_g, spear_g = safe_corr(g["throughput_base"], g["throughput_mobil"])
        print(f"\n  [{label}, n={len(g)}] total throughput: base {tb_g:,.0f} -> "
              f"mobil {tm_g:,.0f} ({tm_g - tb_g:+,.0f}); "
              f"Pearson r={pear_g:.4f} Spearman rho={spear_g:.4f}; "
              f"mean |delta|={g['delta'].abs().mean():.3f} veh/hr")

    def fmt_rows(g):
        lines = []
        for r in g.itertuples():
            nm = name.get((r.u, r.v, r.key)) or "(unnamed)"
            nm = nm if len(nm) <= 27 else nm[:24] + "..."
            lines.append(f"    {nm:<28}{r.u:>12}{r.v:>12}{r.key:>3}"
                        f"{r.throughput_base:>10.1f}{r.throughput_mobil:>10.1f}"
                        f"{r.delta:>+10.1f}  {'multi' if r.multi_lane else 'single'}")
        return lines

    header = (f"    {'street':<28}{'u':>12}{'v':>12}{'k':>3}"
              f"{'base':>10}{'mobil':>10}{'delta':>10}  lanes")
    top_gain = joined.sort_values("delta", ascending=False).head(10)
    print(f"\n  Top 10 gainers by throughput change (mobil - base):\n{header}")
    for line in fmt_rows(top_gain):
        print(line)

    top_lose = joined.sort_values("delta", ascending=True).head(10)
    print(f"\n  Top 10 losers by throughput change (mobil - base):\n{header}")
    for line in fmt_rows(top_lose):
        print(line)


# --- section 4: interaction of the two flags -------------------------------
def interaction_report(runs):
    print("\n" + "=" * 78)
    print("4. INTERACTION -- does realism_both equal the additive prediction?")
    print("=" * 78)
    print("First-ever measurement of the two realism flags interacting: does turning")
    print("on driver heterogeneity AND MOBIL together just add their two separate")
    print("effects (linear, no interaction), or does the combination do something")
    print("the two single-flag deltas don't predict?")

    cols = ["u", "v", "key", "throughput", "mean_speed_mps"]
    b = runs["realism_base"][cols].rename(
        columns={"throughput": "thru_base", "mean_speed_mps": "speed_base"})
    d = runs["realism_drivers"][cols].rename(
        columns={"throughput": "thru_drv", "mean_speed_mps": "speed_drv"})
    m = runs["realism_mobil"][cols].rename(
        columns={"throughput": "thru_mob", "mean_speed_mps": "speed_mob"})
    both = runs["realism_both"][cols].rename(
        columns={"throughput": "thru_both", "mean_speed_mps": "speed_both"})

    j = b.merge(d, on=["u", "v", "key"]).merge(m, on=["u", "v", "key"]).merge(
        both, on=["u", "v", "key"])
    n_mismatch = len(runs["realism_base"]) - len(j)
    if n_mismatch:
        print(f"  WARNING: {n_mismatch} segment(s) lost in the four-way join on "
              f"(u, v, key) -- unexpected, since all four runs share one graph.")

    # additive prediction: base + (drivers - base) + (mobil - base)
    #                     = drivers + mobil - base
    j["thru_pred"] = j["thru_drv"] + j["thru_mob"] - j["thru_base"]

    pear_t, _ = safe_corr(j["thru_both"], j["thru_pred"])
    mad_t = (j["thru_both"] - j["thru_pred"]).abs().median()
    print(f"\n  Throughput: actual 'both' vs additive prediction, "
          f"n={len(j)} segments: Pearson r={pear_t:.4f}  "
          f"median |actual - predicted|={mad_t:.3f} veh/hr")
    print(f"  Network totals: actual both {j['thru_both'].sum():,.0f}  "
          f"predicted {j['thru_pred'].sum():,.0f}  "
          f"({j['thru_both'].sum() - j['thru_pred'].sum():+,.0f})")

    # mean speed is only defined where a segment flowed in ALL FOUR runs; the
    # additive prediction needs all four terms, so rows missing any one speed
    # are dropped from this half of the comparison (they are NOT dropped from
    # the throughput half above, since throughput is always a defined number,
    # zero included).
    speed_cols = ["speed_base", "speed_drv", "speed_mob", "speed_both"]
    speed_ok = j[speed_cols].notna().all(axis=1)
    js = j.loc[speed_ok].copy()
    n_dropped = len(j) - len(js)
    js["speed_pred"] = js["speed_drv"] + js["speed_mob"] - js["speed_base"]

    pear_s, _ = safe_corr(js["speed_both"], js["speed_pred"])
    mad_s = (js["speed_both"] - js["speed_pred"]).abs().median()
    print(f"\n  Mean speed: actual 'both' vs additive prediction, n={len(js)} "
          f"segments flowing in all four runs ({n_dropped} dropped, no speed in "
          f"at least one run): Pearson r={pear_s:.4f}  "
          f"median |actual - predicted|={mad_s * 3.6:.4f} km/h")

    # network-level scalar version of the same additive check: does the
    # network mean speed of 'both' equal base + (drivers-base) + (mobil-base)
    # at the aggregate level too?
    def net_speed(run_df):
        tv = run_df["value"].sum()
        return run_df["v_sum"].sum() / tv if tv > 0 else float("nan")

    ns_base = net_speed(runs["realism_base"])
    ns_drv = net_speed(runs["realism_drivers"])
    ns_mob = net_speed(runs["realism_mobil"])
    ns_both = net_speed(runs["realism_both"])
    ns_pred = ns_drv + ns_mob - ns_base
    print(f"  Network mean speed (km/h): actual both {ns_both * 3.6:.3f}  "
          f"predicted {ns_pred * 3.6:.3f}  "
          f"({(ns_both - ns_pred) * 3.6:+.3f} km/h)")


# --- section 5: caveats -----------------------------------------------------
def print_caveats():
    print("\n" + "=" * 78)
    print("5. CAVEATS")
    print("=" * 78)
    print("""\
  - Corridor scale only (1.5 km radius, 500 vehicles, one seeded hour). None of
    these numbers have been checked at metro scale.
  - MOBIL parameters (politeness, threshold, b_safe) and driver-heterogeneity
    sigmas are a-priori literature values, not calibrated against any held-out
    count. Treat magnitudes as illustrative of DIRECTION, not tuned truth.
  - The Phase 2 noise quadrature treats the run's two accumulated speed moments
    (mean, variance) as if the within-segment speed distribution were Gaussian.
    That is an approximation the two moments alone cannot verify; it is the
    honest first reading they allow, not a claim about the true distribution
    shape.
  - The base run's per-segment speed spread is NOT zero: signals and queues
    create speed variance even with perfectly identical drivers. Phase 2's
    claim is about the DELTA heterogeneity adds on top of that base spread,
    never the raw drivers-run variance read in isolation.""")


def main():
    print("Realism readout: Phase 2 (driver heterogeneity) and Phase 3 (MOBIL) "
          "payoff, corridor scale, seed 42.")

    runs = {}
    for name in RUN_NAMES:
        df = load_run(name)
        df = add_speed_moments(df)
        runs[name] = df

    G = noise.load_network()
    length, name = noise._edge_length_and_name(G)
    lanes = edge_lane_counts(G)

    print_headline_table(runs)
    phase2_report(runs, length, name)
    phase3_report(runs, length, name, lanes)
    interaction_report(runs)
    print_caveats()
    print("\n" + "=" * 78)
    print("End of report.")
    print("=" * 78)


if __name__ == "__main__":
    main()
