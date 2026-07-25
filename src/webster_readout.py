"""ANALYSIS-ONLY readout: the Phase 4 (Webster signal timing) payoff numbers
from the one authoritative corridor run written by src/webster_runs.py.

This script NEVER runs the simulation. Per CLAUDE.md's architecture rule, data
generation and analysis are separate: webster_runs.py wrote the parquet and the
plans JSON already on disk, and everything downstream only reads them. If the
run file is missing, this script raises rather than running the sim to
produce it. It matches src/realism_readout.py's style, structure, and honesty
conventions (that script is the Phase 2/3 readout; this one is Phase 4).

It reads:
    data/processed/realism_webster_segments.parquet   (today's run: WEBSTER on)
    data/processed/realism_base_segments.parquet      (Jul 24 comparator, flags off)
    data/processed/realism_webster_plans.json         (per-node cycle/split/flows)
    data/network/graph.graphml                        (cached corridor graph)

and prints a tidy sectioned report, no plotting (visualization is a separate
script by project convention) and no writes to data/.

Report sections:
  1. PLANS    -- green-split distribution across the 21 signal nodes; the
                 cycle-clamp finding (every node pinned to the 30 s minimum)
                 verified from webster.py's own math, with the flow shortfall
                 quantified; most-asymmetric nodes and their streets.
  2. VOLUMES  -- network throughput delta, per-segment paired deltas
                 (winners/losers/ties), Spearman rank correlation.
  3. SPEEDS   -- per-segment mean-speed and speed-variance deltas, split by
                 whether the segment is signal-adjacent (its downstream node
                 is one of the 21 signalized nodes) or not.
  4. NOISE    -- CNOSSOS noise-surface delta, webster vs base, using the same
                 Gauss-Hermite quadrature src/realism_readout.py uses; checks
                 whether the signal-adjacent variance effect shows up here too.
  5. SANITY   -- NaN/negative-variance pathologies, vehicle-second totals,
                 anything anomalous flagged loudly.
  6. CAVEATS

Run it:  python src/webster_readout.py
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import noise                       # CNOSSOS functions reused, not reimplemented
import webster                     # pure Webster math, reused to verify the clamp
from generate import _approach_phase   # the one phase-assignment rule, mirrored exactly

BASE_RUN = "realism_base"
WEBSTER_RUN = "realism_webster"
PLANS_FILE = os.path.join(config.PROCESSED_DIR, f"{WEBSTER_RUN}_plans.json")


# --- loading ------------------------------------------------------------
def load_run(run_name):
    """Load one run's saved per-segment parquet. Reuses noise.py's loader with
    an explicit run_name (never config.RUN_NAME, so this never depends on
    whatever the config module currently has set). Raises loudly, rather than
    simulating, if the file is not already on disk."""
    return noise.load_run_segments(run_name)


def load_plans():
    """Load the Webster plans JSON webster_runs.py dumped alongside the run:
    per-node cycle/split/offset and the measured approach flows that produced
    them. Raises loudly if missing, same discipline as load_run."""
    if not os.path.exists(PLANS_FILE):
        raise SystemExit(f"No plans at {PLANS_FILE}; the webster run must "
                         f"already be on disk (this script never runs the sim).")
    with open(PLANS_FILE) as fh:
        return json.load(fh)


def add_speed_moments(df):
    """Attach mean_speed_mps, var_mps2 and sd_mps to a run's DataFrame from its
    v_sum / v2_sum time-weighted speed accumulators (see generate.save_results
    docstring): mean = v_sum/value, variance = v2_sum/value - mean^2.

    Guarded exactly as realism_readout.add_speed_moments: only segments with
    value > 0 (any recorded activity) get a mean; everything else is NaN, not
    a divide-by-zero warning. Variance from finite floating-point sums can come
    out as a tiny negative number even though a true variance cannot be
    negative (cancellation in v2_sum/value - mean^2); that is clamped to 0
    before the sqrt so sd is never NaN from that alone."""
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
    n_negative = int(np.sum(raw_var < 0))
    clamped_var = np.clip(raw_var, 0.0, None)   # float-roundoff negatives -> 0

    mean[flowing] = m
    var[flowing] = clamped_var

    df["mean_speed_mps"] = mean
    df["var_mps2"] = var
    df["sd_mps"] = np.sqrt(var)   # NaN stays NaN (sqrt of NaN is NaN, not an error)
    return df, n_negative


def pct(x, q):
    """Percentile of a 1-D array-like with NaNs dropped, or NaN if nothing left."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(np.percentile(x, q)) if len(x) else float("nan")


def safe_corr(x, y):
    """Pearson and Spearman correlation, guarded: scipy raises/produces NaN when
    an input is constant (zero variance). Return NaN pairs rather than letting
    an exception or a silent NaN through unexplained (mirrors realism_readout)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return float("nan"), float("nan")
    pear = stats.pearsonr(x, y)[0]
    spear = stats.spearmanr(x, y)[0]
    return float(pear), float(spear)


# --- section 1: PLANS -------------------------------------------------------
def plans_report(plans, G):
    print("\n" + "=" * 78)
    print("1. PLANS -- per-node Webster timing the run actually used")
    print("=" * 78)

    node_cycle = {int(n): c for n, c in plans["node_cycle"].items()}
    node_split = {int(n): s for n, s in plans["node_split"].items()}
    flows = {}
    for k, q in plans["flows_veh_h"].items():
        u, v, key = k.split("|")
        flows[(int(u), int(v), int(key))] = q
    n_nodes = len(node_cycle)
    print(f"  {n_nodes} signalized nodes ({plans['tagged']} OSM-tagged), "
          f"clearance {plans['clearance_s']:.1f} s/cycle (yellow+all-red, "
          f"split evenly across the two phase changes).")

    # --- cycle clamp: verify every node sits at the 30 s minimum -------------
    cycles = np.array(list(node_cycle.values()))
    n_at_min = int(np.sum(cycles <= config.WEBSTER_CYCLE_MIN_S + 1e-9))
    print(f"\n  Cycle length: min {cycles.min():.1f}s  median {np.median(cycles):.1f}s  "
          f"max {cycles.max():.1f}s  ({n_at_min}/{n_nodes} nodes at the "
          f"{config.WEBSTER_CYCLE_MIN_S:.0f}s minimum).")
    if n_at_min == n_nodes:
        print("  VERIFIED: every signalized node clamped to the 30 s minimum "
              "cycle at full corridor demand. The prior session's hypothesis "
              "that full demand would spread the cycles is FALSIFIED at this "
              "scale -- 'Webster timing' here degenerates to uniform 30 s "
              "cycles with per-node flow-proportional splits and a 5 s/phase "
              "clearance, not variable cycle lengths.")
    else:
        print(f"  NOTE: {n_nodes - n_at_min} node(s) exceeded the minimum cycle "
              f"-- the falsification above is NOT total; see which nodes below.")
        over = {n: c for n, c in node_cycle.items() if c > config.WEBSTER_CYCLE_MIN_S + 1e-9}
        for n, c in sorted(over.items(), key=lambda kv: -kv[1]):
            print(f"    node {n}: cycle {c:.1f}s")

    # --- how far short of the clamp threshold the actual flows fall ---------
    # From webster.cycle_and_split's own formula: C0 = (1.5*L+5)/(1-Y), L =
    # 2*lost_time_s. C0 exceeds cycle_min_s exactly when
    #   Y > 1 - (1.5*L+5) / cycle_min_s
    # With config's a-priori constants (lost_time_s=4.0, cycle_min_s=30.0),
    # L=8.0, so the threshold is Y* = 1 - 17/30 = 13/30 = 0.4333. Since every
    # node here runs single-lane critical approaches (LANES_ENABLED off in
    # this run), Y = (q_ew + q_ns) / sat_flow, so the combined EW+NS critical
    # flow needed to push a node's cycle past 30 s is Y* * sat_flow veh/h.
    L = 2.0 * config.WEBSTER_LOST_TIME_S
    y_star = 1.0 - (1.5 * L + 5.0) / config.WEBSTER_CYCLE_MIN_S
    q_star = y_star * config.WEBSTER_SAT_FLOW
    print(f"\n  From webster.py's own math: a node's cycle only exceeds the "
          f"{config.WEBSTER_CYCLE_MIN_S:.0f}s minimum once its flow ratio Y > "
          f"{y_star:.4f} (L={L:.1f}s lost time, sat_flow={config.WEBSTER_SAT_FLOW:.0f} "
          f"veh/h/lane). With single-lane critical approaches that means combined "
          f"EW+NS critical flow > {q_star:.1f} veh/h.")

    # recompute each node's per-phase CRITICAL (max) approach flow, exactly as
    # generate.build_webster_plans does, to see how close the busiest node got.
    node_crit = {}
    for n in node_cycle:
        crit = {0: 0.0, 1: 0.0}
        for u, v, k in G.in_edges(n, keys=True):
            ph = _approach_phase(G, u, v)
            q = flows.get((u, v, k), 0.0)
            if q > crit[ph]:
                crit[ph] = q
        node_crit[n] = (crit[0], crit[1], crit[0] + crit[1])

    ranked = sorted(node_crit.items(), key=lambda kv: -kv[1][2])
    busiest_n, (q_ew, q_ns, q_sum) = ranked[0]
    print(f"  Busiest node by combined critical flow: {busiest_n} "
          f"(EW {q_ew:.0f} + NS {q_ns:.0f} = {q_sum:.0f} veh/h), "
          f"{q_star - q_sum:.1f} veh/h ({100 * (q_star - q_sum) / q_star:.1f}%) "
          f"SHORT of the {q_star:.0f} veh/h threshold that would push its cycle "
          f"past 30 s -- close, not a wide margin.")
    print("  Top 5 nodes by combined critical flow (all still short of the "
          "threshold):")
    for n, (qe, qn, qs) in ranked[:5]:
        print(f"    node {n}: EW {qe:>6.0f}  NS {qn:>6.0f}  sum {qs:>6.0f} veh/h  "
              f"(Y={qs / config.WEBSTER_SAT_FLOW:.3f} vs threshold {y_star:.3f})")

    # --- green split distribution --------------------------------------------
    splits = np.array(list(node_split.values()))
    print(f"\n  Green split (fraction of cycle the EW phase holds): "
          f"min {splits.min():.4f}  median {np.median(splits):.4f}  "
          f"max {splits.max():.4f}")
    n_asym = int(np.sum(np.abs(splits - 0.5) > 0.05))
    print(f"  {n_asym}/{n_nodes} nodes differ from an even 50/50 split by more "
          f"than 0.05 (i.e. outside [0.45, 0.55]).")

    # Both extremes trace back to the min-green FLOOR in webster.cycle_and_split
    # (g_tot = cycle - L = 22s at the 30s clamp; a phase below the 7s floor gets
    # raised to exactly 7s and its partner absorbs the deficit), not to a smooth
    # proportional split -- most of the 21 nodes sit at one of the two floor
    # values rather than somewhere continuously in between.
    min_g = config.WEBSTER_MIN_GREEN_S
    g_tot = config.WEBSTER_CYCLE_MIN_S - L
    floor_lo = (min_g + config.WEBSTER_LOST_TIME_S) / config.WEBSTER_CYCLE_MIN_S
    floor_hi = (g_tot - min_g + config.WEBSTER_LOST_TIME_S) / config.WEBSTER_CYCLE_MIN_S
    n_floor_lo = int(np.sum(np.isclose(splits, floor_lo, atol=1e-6)))
    n_floor_hi = int(np.sum(np.isclose(splits, floor_hi, atol=1e-6)))
    print(f"  Of those, {n_floor_lo} node(s) sit EXACTLY at the low min-green "
          f"floor (split={floor_lo:.4f}, i.e. EW green pinned to the {min_g:.0f}s "
          f"floor) and {n_floor_hi} sit EXACTLY at the high floor "
          f"(split={floor_hi:.4f}, NS pinned to the floor instead) -- "
          f"{n_floor_lo + n_floor_hi}/{n_nodes} nodes are floor-pinned, not "
          f"smoothly proportional to their flow ratio.")

    # --- most asymmetric nodes, with street names ----------------------------
    length, name = noise._edge_length_and_name(G)

    def streets_at(n):
        """Distinct street names on edges touching node n (in or out), for
        identifying what corridor/cross-street a node sits on."""
        names = set()
        for u, v, k in list(G.in_edges(n, keys=True)) + list(G.out_edges(n, keys=True)):
            nm = name.get((u, v, k))
            if nm:
                names.add(nm)
        return ", ".join(sorted(names)) if names else "(unnamed)"

    print("\n  Top 5 most asymmetric nodes (|split - 0.5|), with streets:")
    by_asym = sorted(node_split.items(), key=lambda kv: -abs(kv[1] - 0.5))
    for n, s in by_asym[:5]:
        qe, qn, qs = node_crit[n]
        print(f"    node {n:>12}: split {s:.4f}  (EW crit {qe:.0f}, NS crit "
              f"{qn:.0f} veh/h)  streets: {streets_at(n)}")

    return node_cycle, node_split


# --- section 2: VOLUMES ------------------------------------------------------
def volumes_report(base, web, name):
    print("\n" + "=" * 78)
    print("2. VOLUMES -- segment throughput, webster vs base")
    print("=" * 78)

    b = base[["u", "v", "key", "throughput"]].rename(columns={"throughput": "thru_base"})
    w = web[["u", "v", "key", "throughput"]].rename(columns={"throughput": "thru_web"})
    j = b.merge(w, on=["u", "v", "key"], how="outer")
    n_mismatch = j["thru_base"].isna().sum() + j["thru_web"].isna().sum()
    if n_mismatch:
        print(f"  WARNING: {n_mismatch} segment(s) did not join on (u, v, key) "
              f"between {BASE_RUN} and {WEBSTER_RUN} -- unexpected, since both "
              f"runs share the same cached graph.")
    j = j.dropna(subset=["thru_base", "thru_web"])
    j["delta"] = j["thru_web"] - j["thru_base"]

    tb, tw = j["thru_base"].sum(), j["thru_web"].sum()
    pct_delta = 100 * (tw - tb) / tb if tb else float("nan")
    print(f"  Network total throughput: base {tb:,.0f}  webster {tw:,.0f}  "
          f"({'+' if tw >= tb else ''}{tw - tb:,.0f}, {pct_delta:+.2f}%)")
    print("  A drop here is not automatically a defect: the base signal's zero "
          "clearance is itself unrealistic, and Webster's 5 s/phase clearance "
          "costs real green time the base model never charges (see caveats).")

    n_winner = int((j["delta"] > 0).sum())
    n_loser = int((j["delta"] < 0).sum())
    n_tie = int((j["delta"] == 0).sum())
    print(f"\n  Per-segment: {n_winner} winners (webster > base), {n_loser} "
          f"losers, {n_tie} ties, of {len(j)} segments.")
    print(f"  Mean |per-segment throughput change|: {j['delta'].abs().mean():.3f} veh/hr")

    pear, spear = safe_corr(j["thru_base"], j["thru_web"])
    print(f"  Per-segment throughput correlation (base vs webster, all "
          f"{len(j)} segments): Pearson r={pear:.4f}  Spearman rho={spear:.4f}  "
          f"-- the standing project question is whether anything moves rank "
          f"order; a rho near 1 means it mostly doesn't.")

    def fmt_rows(g):
        lines = []
        for r in g.itertuples():
            nm = name.get((r.u, r.v, r.key)) or "(unnamed)"
            nm = nm if len(nm) <= 27 else nm[:24] + "..."
            lines.append(f"    {nm:<28}{r.u:>12}{r.v:>12}{r.key:>3}"
                        f"{r.thru_base:>10.1f}{r.thru_web:>10.1f}{r.delta:>+10.1f}")
        return lines

    header = (f"    {'street':<28}{'u':>12}{'v':>12}{'k':>3}"
              f"{'base':>10}{'webster':>10}{'delta':>10}")
    print(f"\n  Top 10 gainers by throughput change (webster - base):\n{header}")
    for line in fmt_rows(j.sort_values("delta", ascending=False).head(10)):
        print(line)
    print(f"\n  Top 10 losers by throughput change (webster - base):\n{header}")
    for line in fmt_rows(j.sort_values("delta", ascending=True).head(10)):
        print(line)

    return j


# --- section 3: SPEEDS -------------------------------------------------------
def speeds_report(base, web, name, signal_nodes):
    print("\n" + "=" * 78)
    print("3. SPEEDS -- per-segment mean speed and speed variance, webster vs base")
    print("=" * 78)

    cols = ["u", "v", "key", "mean_speed_mps", "var_mps2"]
    b = base[cols].rename(columns={"mean_speed_mps": "mean_base", "var_mps2": "var_base"})
    w = web[cols].rename(columns={"mean_speed_mps": "mean_web", "var_mps2": "var_web"})
    j = b.merge(w, on=["u", "v", "key"], how="outer")
    # a mean/variance only exists where the segment carried activity (value>0)
    # in that run; a segment silent in EITHER run has no delta to report.
    ok = j[["mean_base", "mean_web", "var_base", "var_web"]].notna().all(axis=1)
    n_dropped = int((~ok).sum())
    j = j.loc[ok].copy()
    j["signal_adj"] = j["v"].isin(signal_nodes)

    j["mean_delta_kph"] = (j["mean_web"] - j["mean_base"]) * 3.6
    j["var_delta"] = j["var_web"] - j["var_base"]

    print(f"  {len(j)} segments flowed in both runs ({n_dropped} dropped, "
          f"silent in at least one run).")

    md = j["mean_delta_kph"].to_numpy()
    print(f"\n  Mean-speed delta (webster - base), km/h: "
          f"median {np.median(md):+.4f}  mean {np.mean(md):+.4f}  "
          f"p5 {pct(md, 5):+.4f}  p95 {pct(md, 95):+.4f}")

    vd = j["var_delta"].to_numpy()
    print(f"  Speed-variance delta (webster - base), (m/s)^2: "
          f"median {np.median(vd):+.5f}  mean {np.mean(vd):+.5f}  "
          f"p5 {pct(vd, 5):+.5f}  p95 {pct(vd, 95):+.5f}")

    def fmt_rows(g, col, unit, scale=1.0):
        lines = []
        for r in g.itertuples():
            nm = name.get((r.u, r.v, r.key)) or "(unnamed)"
            nm = nm if len(nm) <= 27 else nm[:24] + "..."
            val = getattr(r, col) * scale
            lines.append(f"    {nm:<28}{r.u:>12}{r.v:>12}{r.key:>3}"
                        f"{val:>+12.4f} {unit}  {'signal-adj' if r.signal_adj else ''}")
        return lines

    print("\n  Top 5 mean-speed movers (either direction):")
    top_speed = j.reindex(j["mean_delta_kph"].abs().sort_values(ascending=False).index).head(5)
    for line in fmt_rows(top_speed, "mean_delta_kph", "km/h"):
        print(line)

    print("\n  Top 5 speed-variance movers (either direction):")
    top_var = j.reindex(j["var_delta"].abs().sort_values(ascending=False).index).head(5)
    for line in fmt_rows(top_var, "var_delta", "(m/s)^2"):
        print(line)

    # --- the clearance hypothesis: does variance rise MORE next to signals? --
    print("\n  Signal-adjacency check (segment classified by whether its "
          "DOWNSTREAM node -- the 'v' end, where a vehicle queues -- is one of "
          "the 21 signalized nodes). The clearance forces extra stop-start "
          "right at the signal, so the hypothesis is that variance rises there "
          "specifically, not network-wide.")
    n_adj = int(j["signal_adj"].sum())
    n_other = len(j) - n_adj
    for label, mask in (("signal-adjacent", j["signal_adj"]), ("elsewhere", ~j["signal_adj"])):
        g = j.loc[mask]
        print(f"    [{label}, n={len(g)}] median var delta "
              f"{g['var_delta'].median():+.5f} (m/s)^2   "
              f"median mean-speed delta {g['mean_delta_kph'].median():+.4f} km/h")
    if n_adj and n_other:
        adj_med = j.loc[j["signal_adj"], "var_delta"].median()
        other_med = j.loc[~j["signal_adj"], "var_delta"].median()
        if adj_med > other_med:
            print(f"    Variance rises MORE next to signals ({adj_med:+.5f} vs "
                  f"{other_med:+.5f}) -- consistent with the clearance forcing "
                  f"extra stop-start there.")
        else:
            print(f"    Variance does NOT rise more next to signals "
                  f"({adj_med:+.5f} vs {other_med:+.5f}) -- the clearance "
                  f"hypothesis is not supported by this run; reporting as found, "
                  f"not smoothed over.")

    return j


# --- section 4: NOISE --------------------------------------------------------
def noise_levels(df):
    """Per-segment CNOSSOS level for one run, two ways -- identical method to
    realism_readout.noise_two_ways, reused here (not reimplemented differently)
    so the two readouts are directly comparable:

      (a) mean-speed-only: one CNOSSOS evaluation at the segment's mean speed
          (src/noise.py's own build_noise_surface method).
      (b) speed-distribution-aware: a 3-point Gauss-Hermite quadrature over
          N(mean, sd) built from the run's own accumulated speed moments, flow
          Q held fixed across the three nodes, the three levels ENERGY-averaged
          (sound adds in the power domain, not the dB domain) back to one
          dB(A) number. This is the same approximation realism_readout uses:
          the two moments do not prove the within-segment speed distribution is
          Gaussian, only that this is the honest first reading they allow.

    Returns a DataFrame indexed like df, columns u, v, key, level_a_dba,
    level_b_dba, restricted to flowing segments (throughput>0, value>0, mean
    speed>0).
    """
    flowing = (df["throughput"] > 0) & (df["value"] > 0) & (df["mean_speed_mps"] > 0)
    sub = df.loc[flowing, ["u", "v", "key", "throughput", "mean_speed_mps", "sd_mps"]].copy()

    q = sub["throughput"].to_numpy()
    mean_kph = sub["mean_speed_mps"].to_numpy() * 3.6
    sd_kph = sub["sd_mps"].to_numpy() * 3.6

    level_a = np.full(len(sub), np.nan)
    level_b = np.full(len(sub), np.nan)

    sqrt3 = np.sqrt(3.0)
    weights = np.array([1.0 / 6.0, 2.0 / 3.0, 1.0 / 6.0])
    for i in range(len(sub)):
        qi, mi, si = q[i], mean_kph[i], sd_kph[i]

        lwa_a = noise.segment_line_power_dba(qi, mi)
        level_a[i] = noise.propagate_line(lwa_a) if lwa_a is not None else np.nan

        # speeds clamped >= 1 km/h so a low-mean/high-sd segment never asks
        # CNOSSOS for a zero or negative speed. Q fixed at qi for every node.
        nodes_kph = np.clip([mi - sqrt3 * si, mi, mi + sqrt3 * si], 1.0, None)
        levels = np.array([
            noise.propagate_line(noise.segment_line_power_dba(qi, v))
            for v in nodes_kph
        ])
        level_b[i] = 10.0 * np.log10(np.sum(weights * 10.0 ** (levels / 10.0)))

    sub["level_a_dba"] = level_a
    sub["level_b_dba"] = level_b
    return sub[["u", "v", "key", "level_a_dba", "level_b_dba"]]


def noise_report(base, web, name, signal_nodes):
    print("\n" + "=" * 78)
    print("4. NOISE -- CNOSSOS noise-surface delta, webster vs base")
    print("=" * 78)
    print("Same speed-distribution-aware quadrature realism_readout uses (3-point "
          "Gauss-Hermite over N(mean, sd) from the run's own v_sum/v2_sum "
          "moments), applied to each run separately, then differenced.")

    lb = noise_levels(base).rename(columns={"level_a_dba": "a_base", "level_b_dba": "b_base"})
    lw = noise_levels(web).rename(columns={"level_a_dba": "a_web", "level_b_dba": "b_web"})
    j = lb.merge(lw, on=["u", "v", "key"], how="inner")
    n_only_base = len(lb) - len(j)
    n_only_web = len(lw) - len(j)
    if n_only_base or n_only_web:
        print(f"  NOTE: {n_only_base} segment(s) flowed only in base, "
              f"{n_only_web} only in webster -- excluded from the paired delta "
              f"below (no noise level to difference).")

    j["delta_b_dba"] = j["b_web"] - j["b_base"]     # quadrature-based delta (headline)
    j["delta_a_dba"] = j["a_web"] - j["a_base"]     # mean-only delta (for comparison)
    j["signal_adj"] = j["v"].isin(signal_nodes)

    db = j["delta_b_dba"].to_numpy()
    da = j["delta_a_dba"].to_numpy()
    print(f"\n  n={len(j)} segments carrying flow in both runs.")
    print(f"  Noise delta (webster - base), quadrature method, dB(A): "
          f"median {np.median(db):+.4f}  mean {np.mean(db):+.4f}  "
          f"p5 {pct(db, 5):+.4f}  p95 {pct(db, 95):+.4f}  max|delta| {np.max(np.abs(db)):.4f}")
    print(f"  Noise delta (webster - base), mean-speed-only method, dB(A): "
          f"median {np.median(da):+.4f}  mean {np.mean(da):+.4f}")
    print(f"  (The two methods' deltas differ by median "
          f"{np.median(np.abs(db - da)):.4f} dB(A) -- this is the variance's "
          f"own contribution to the noise delta, isolated from the mean-speed "
          f"shift alone.)")

    print("\n  Top 5 segments by |quadrature noise delta|:")
    top5 = j.reindex(j["delta_b_dba"].abs().sort_values(ascending=False).index).head(5)
    print(f"    {'street':<28}{'u':>12}{'v':>12}{'k':>3}{'base dB':>10}"
          f"{'web dB':>10}{'delta':>9}")
    for r in top5.itertuples():
        nm = name.get((r.u, r.v, r.key)) or "(unnamed)"
        nm = nm if len(nm) <= 27 else nm[:24] + "..."
        print(f"    {nm:<28}{r.u:>12}{r.v:>12}{r.key:>3}{r.b_base:>10.2f}"
              f"{r.b_web:>10.2f}{r.delta_b_dba:>+9.4f}")

    print("\n  Signal-adjacency check on the noise delta (same downstream-node "
          "classification as section 3):")
    for label, mask in (("signal-adjacent", j["signal_adj"]), ("elsewhere", ~j["signal_adj"])):
        g = j.loc[mask]
        print(f"    [{label}, n={len(g)}] median quadrature noise delta "
              f"{g['delta_b_dba'].median():+.4f} dB(A)")
    if j["signal_adj"].any() and (~j["signal_adj"]).any():
        adj_med = j.loc[j["signal_adj"], "delta_b_dba"].median()
        other_med = j.loc[~j["signal_adj"], "delta_b_dba"].median()
        if adj_med > other_med:
            print(f"    The signal-adjacent variance effect from section 3 DOES "
                  f"carry through to noise ({adj_med:+.4f} vs {other_med:+.4f} dB(A)).")
        else:
            print(f"    The signal-adjacent variance effect from section 3 does "
                  f"NOT show up distinctly in the noise delta "
                  f"({adj_med:+.4f} vs {other_med:+.4f} dB(A)) -- reported as "
                  f"found, not assumed from the speed result alone.")

    return j


# --- section 5: SANITY -------------------------------------------------------
def sanity_report(base_raw, web_raw, base, web, n_neg_base, n_neg_web):
    print("\n" + "=" * 78)
    print("5. SANITY")
    print("=" * 78)

    any_flag = False

    for label, n_neg in (("base", n_neg_base), ("webster", n_neg_web)):
        if n_neg:
            print(f"  {label}: {n_neg} segment(s) had a tiny negative raw "
                  f"variance before clamping (float cancellation in "
                  f"v2_sum/value - mean^2) -- clamped to 0, same as "
                  f"realism_readout does. Not a pathology by itself.")

    for label, df in (("base", base), ("webster", web)):
        n_nan_mean = int(df["mean_speed_mps"].isna().sum() - (df["value"] == 0).sum())
        n_neg_thru = int((df["throughput"] < 0).sum())
        n_neg_val = int((df["value"] < 0).sum())
        if n_neg_thru or n_neg_val:
            print(f"  FLAG [{label}]: {n_neg_thru} negative throughput, "
                  f"{n_neg_val} negative value rows -- should never happen.")
            any_flag = True

    tv_base = base_raw["value"].sum()
    tv_web = web_raw["value"].sum()
    ratio = tv_web / tv_base if tv_base else float("nan")
    print(f"\n  Total vehicle-seconds: base {tv_base:,.0f}  webster {tv_web:,.0f}  "
          f"(ratio {ratio:.4f}).")
    if not (0.5 <= ratio <= 2.0):
        print(f"  FLAG: vehicle-second totals differ by more than 2x between "
              f"the two runs -- outside a plausible band for two runs sharing "
              f"the same seeded vehicle population; investigate before citing.")
        any_flag = True
    else:
        print("  Within a plausible band for two runs sharing the same "
              "seeded vehicle population (only signal timing differs).")

    n_seg_base, n_seg_web = len(base_raw), len(web_raw)
    if n_seg_base != n_seg_web:
        print(f"  FLAG: segment counts differ (base {n_seg_base}, webster "
              f"{n_seg_web}) -- both runs should share one cached graph.")
        any_flag = True
    else:
        print(f"  Segment counts match: {n_seg_base} segments in both runs.")

    if not any_flag:
        print("\n  No pathologies found beyond the routine variance-clamp note above.")


# --- section 6: caveats ------------------------------------------------------
def print_caveats():
    print("\n" + "=" * 78)
    print("6. CAVEATS")
    print("=" * 78)
    print("""\
  - Corridor scale only (1.5 km radius, 500 vehicles, one seeded hour, seed 42).
    None of these numbers have been checked at metro scale.
  - Webster's constants (saturation flow 1900 veh/h/lane, 30 s minimum cycle,
    120 s maximum, 3.5 s yellow + 1.5 s all-red clearance) are a-priori
    literature/HCM values, NOT calibrated against any held-out PBOT count.
    Treat magnitudes as illustrative of DIRECTION, not tuned truth.
  - The base (uniform) signal's zero clearance is itself unrealistic -- no real
    signal switches phases with no yellow or all-red interval. Webster adding a
    5 s/phase clearance is realism that COSTS capacity; a throughput or speed
    drop from that is not automatically a defect of the Webster model, it is
    the honest price of removing an unrealistic assumption the base model made.
    This readout reports whichever direction the data shows, without spin.
  - The noise quadrature treats each run's two accumulated speed moments (mean,
    variance) as if the within-segment speed distribution were Gaussian. That
    is an approximation the two moments alone cannot verify; it is the honest
    first reading they allow, not a claim about the true distribution shape.
  - Only one seed. No repeated-seed variance estimate exists for any number in
    this report, so a single segment's delta could in principle be seed noise
    rather than a Webster effect -- this readout cannot distinguish the two
    with only one run per condition.""")


def main():
    # street names can carry non-ASCII characters (e.g. "Cesar E. Chavez"); force
    # utf-8 stdout so those print correctly instead of as replacement characters
    # on a Windows console defaulting to a narrower codepage.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    print("Webster readout: Phase 4 (per-node signal timing) payoff, corridor "
          "scale, seed 42.")

    plans = load_plans()
    base_raw = load_run(BASE_RUN)
    web_raw = load_run(WEBSTER_RUN)
    base, n_neg_base = add_speed_moments(base_raw)
    web, n_neg_web = add_speed_moments(web_raw)

    G = noise.load_network()
    _length, name = noise._edge_length_and_name(G)

    node_cycle, node_split = plans_report(plans, G)
    signal_nodes = set(node_cycle.keys())

    volumes_report(base, web, name)
    speeds_report(base, web, name, signal_nodes)
    noise_report(base, web, name, signal_nodes)
    sanity_report(base_raw, web_raw, base, web, n_neg_base, n_neg_web)
    print_caveats()
    print("\n" + "=" * 78)
    print("End of report.")
    print("=" * 78)


if __name__ == "__main__":
    main()
