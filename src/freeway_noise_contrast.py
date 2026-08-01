"""NO2 versus noise from the SAME I-205 closure: do the two surfaces disagree?

The mentor's open question (Jul 30, asked after hearing the argument and again by
email Jul 31): is there a good story combining the pollution and the noise, or are
they two papers? The argument on the table is that they are near-opposites, because
noise falls off fast with distance while NO2 accumulates, so moving traffic onto a
residential street is a bigger deal for noise than the same move is for NO2.

That is an assertion until it is measured. This script measures it, on the closure
campaign already on disk: same runs, same paired 8-seed design, same pre-set bar as
src/freeway_multiseed.py, but reporting BOTH surfaces per street side by side. Where
the two columns rank streets differently, the surfaces genuinely disagree and the
combined story has evidence. Where they move together, they do not, and that is the
honest answer to give.

Reads only saved files (the 24 fwms parquets, the summaries, the cached graph) and
runs no simulation, per the single-source-of-truth rule.

TWO THINGS THIS SCRIPT IS CAREFUL ABOUT:

1. Decibels are a logarithm and MUST NOT be summed or averaged like grams. Grams of
   NO2 are extensive: a street's total is the sum over its segments. A dB value is a
   level, so combining segments means going back to acoustic energy, weighting each
   segment's per-metre energy by its length (total energy / total length; an unweighted
   sum of per-metre energies would make the level depend on how OSM segmented the
   street), and converting back. The energy-domain combination is also how CNOSSOS
   combines its own octave bands, so the idiom matches noise.py. The levels are SOURCE
   levels (no propagation step); the constant receiver offset cancels in every paired
   difference reported here, and no absolute dB from this script is ever citable.

2. A segment can be silent (no flow, noise_db = NaN) on one side of the pair. Dropping
   those would quietly bias the answer toward "noise did not change", since a street
   that goes from empty to busy is exactly the effect being looked for. In energy terms
   silence is simply zero, which combines correctly, so silent segments are carried as
   zero energy rather than discarded. A street with no finite level pair in some seed
   keeps its row (the NO2 column is still real) but gets no noise verdict, only its
   on/off seed count: the pre-set unanimity bar assumes the full seed set.

    python src/freeway_noise_contrast.py            # the contrast table
    python src/freeway_noise_contrast.py --verify   # check the vectorized CNOSSOS
"""
import argparse
import json
import os
import sys

import numpy as np
import osmnx as ox
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config             # noqa: E402
import noise              # noqa: E402  (the verified CNOSSOS coefficients)
from freeway_multiseed import SEEDS, run_name, summary_path   # noqa: E402

NEAR_KM = 2.0        # same near-field cut as the NO2 readout, set from the measured
                     # distance decay in freeway_closure_analysis.py, not tuned here
ARMS = ("abernethy", "powell")


# --- vectorized CNOSSOS ------------------------------------------------------
# noise.build_noise_surface loops row by row, which is fine for one run and far too
# slow for 24 (159,425 segments each, so ~3.8M scalar calls). Same formula, same
# coefficients, evaluated on arrays. --verify checks it against the scalar reference
# element by element, which is the same discipline the vectorized haversine got.

def segment_line_power_dba_vec(q_vph, v_kph):
    """A-weighted line-source sound power per metre, dB(A), for arrays of flow and
    speed. Mirrors noise.segment_line_power_dba exactly, including the V_FLOOR_KPH
    floor on the source term and the TRUE speed in the flow term. Returns NaN where
    there is no flow, matching the scalar function's None."""
    q = np.asarray(q_vph, dtype=float)
    v = np.asarray(v_kph, dtype=float)
    ok = (q > 0) & (v > 0)

    v_src = np.maximum(v, noise.V_FLOOR_KPH)[:, None]      # (n, 1) against (8,) bands
    lwr = noise.AR_CAT1 + noise.BR_CAT1 * np.log10(v_src / noise.V_REF_KPH)
    lwp = noise.AP_CAT1 + noise.BP_CAT1 * (v_src - noise.V_REF_KPH) / noise.V_REF_KPH
    lw_band = 10.0 * np.log10(10.0 ** (lwr / 10.0) + 10.0 ** (lwp / 10.0))

    with np.errstate(divide="ignore", invalid="ignore"):
        flow_term = 10.0 * np.log10(q / (1000.0 * v))
    lw_line = lw_band + flow_term[:, None]
    # no-flow rows carry flow_term = -inf and log10(0) below; they are masked out by
    # `ok` immediately after, so the warning they raise is noise, not a problem
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 10.0 * np.log10(
            np.sum(10.0 ** ((lw_line + noise.A_WEIGHTING_DB) / 10.0), axis=1))
    return np.where(ok, out, np.nan)


def verify_vectorized(n=4000, seed=0):
    """Element-by-element check of the vectorized CNOSSOS against noise.py's scalar
    reference, over the speed and flow ranges the campaign actually produces."""
    rng = np.random.default_rng(seed)
    q = rng.uniform(0.0, 4000.0, n)
    v = rng.uniform(0.0, 130.0, n)
    q[:50], v[50:100] = 0.0, 0.0                      # exercise the no-flow branch
    got = segment_line_power_dba_vec(q, v)
    ref = np.array([
        (lambda r: np.nan if r is None else r)(noise.segment_line_power_dba(qi, vi))
        for qi, vi in zip(q, v)])
    both_nan = np.isnan(got) & np.isnan(ref)
    diff = np.abs(np.where(both_nan, 0.0, got - ref))
    bad = int(np.sum(~both_nan & ~np.isfinite(diff)))
    print(f"vectorized CNOSSOS vs noise.segment_line_power_dba over {n} samples:")
    print(f"  max abs difference : {np.nanmax(diff):.3e} dB")
    print(f"  NaN agreement      : {int(both_nan.sum())} both-NaN, {bad} mismatched")
    ok = np.nanmax(diff) < 1e-9 and bad == 0
    print("  VERIFIED IDENTICAL" if ok else "  MISMATCH, do not use")
    return ok


# --- surfaces per run --------------------------------------------------------

def load_geo(G):
    """Per-edge midpoint, length and street name, indexed like the parquets."""
    recs = []
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0] if nm else None
        recs.append((u, v, k,
                     0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])),
                     0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])),
                     float(d.get("length", 10.0) or 10.0),
                     str(nm) if nm else "(unnamed)"))
    return pd.DataFrame(
        recs, columns=["u", "v", "key", "lat", "lon", "length_m", "name"]
    ).set_index(["u", "v", "key"])


def haversine_km(lat0, lon0, lat, lon):
    """Great-circle km, same formula as generate._haversine_m."""
    r = 6_371_000.0
    p1, p2 = np.radians(lat0), np.radians(lat)
    dp, dl = np.radians(lat - lat0), np.radians(lon - lon0)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a)) / 1000.0


def surface(arm, seed, geo):
    """One run's per-segment NO2 grams and acoustic energy per metre.

    Energy, not dB, is what leaves this function: it is the quantity that combines
    additively across segments, so every downstream aggregation is a plain sum and
    the log only reappears at the very end.
    """
    p = os.path.join(config.PROCESSED_DIR, f"{run_name(arm, seed)}_segments.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p).set_index(["u", "v", "key"])
    df = df.join(geo[["length_m"]], how="left")

    q = df["throughput"].astype(float).to_numpy()
    val = df["value"].astype(float).to_numpy()
    L = df["length_m"].to_numpy()
    # congestion-aware realized speed, identical recovery to noise.build_noise_surface
    with np.errstate(divide="ignore", invalid="ignore"):
        v_mps = np.where((q > 0) & (val > 0), L * q / np.where(val > 0, val, np.nan),
                         np.nan)
    db = segment_line_power_dba_vec(q, v_mps * 3.6)

    # dB -> acoustic energy per metre; a silent segment is zero energy, not NaN,
    # because "no traffic noise" combines with neighbours as nothing, not as missing.
    # NOTE these are SOURCE levels (no propagate_line step): every level below is
    # therefore offset from a receiver level by the same constant, which cancels in
    # the paired differences this script reports. Never quote an absolute dB from it.
    e_per_m = np.where(np.isnan(db), 0.0, 10.0 ** (np.nan_to_num(db) / 10.0))
    # energy per metre x metres = the segment's total acoustic energy contribution;
    # this, not e_per_m, is what sums physically across segments (audit finding 1:
    # summing per-metre energies made a street's level depend on how OSM happened
    # to segment it, ~19 dB of pure segmentation artifact in a hand check)
    df["energy_len"] = e_per_m * L
    df["no2_g"] = config.F_NO2 * df["nox_g"].astype(float)
    return df[["no2_g", "energy_len", "length_m"]]


def street_levels(df, removed):
    """Aggregate to streets: NO2 grams summed, noise combined in energy then logged.

    The noise number is the length-weighted mean energy per metre along the street,
    expressed as a level. That is 'what a receiver beside a typical stretch of this
    street hears', and unlike a mean of dB values it is physically meaningful.
    """
    d = df[~df.index.isin(set(removed))]
    g = d.groupby("name").agg(no2_g=("no2_g", "sum"),
                              energy_len=("energy_len", "sum"),
                              length_m=("length_m", "sum"))
    # total acoustic energy / total length = length-weighted mean energy per metre,
    # independent of segmentation (audit finding 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        g["level_db"] = 10.0 * np.log10(g["energy_len"] / g["length_m"])
    return g              # level_db is -inf on a wholly silent street, by design


def collect(arm, geo, near_km=NEAR_KM):
    """Per-street paired differences across seeds: NO2 grams and noise dB."""
    per_seed, used = {}, 0
    for s in SEEDS:
        o, c = surface("open", s, geo), surface(arm, s, geo)
        if o is None or c is None:
            continue
        with open(summary_path(arm, s)) as fh:
            removed = [tuple(e) for e in json.load(fh)["removed"]]
        rem = geo.loc[geo.index.intersection(removed)]
        clat, clon = rem.lat.mean(), rem.lon.mean()

        near_idx = geo.index[haversine_km(clat, clon, geo.lat.values,
                                          geo.lon.values) <= near_km]
        oj = o.join(geo[["name"]]).loc[o.index.intersection(near_idx)]
        cj = c.join(geo[["name"]]).loc[c.index.intersection(near_idx)]
        go, gc = street_levels(oj, removed), street_levels(cj, removed)

        j = go.join(gc, how="inner", lsuffix="_o", rsuffix="_c")
        for nm, r in j.iterrows():
            # A street silent on ONE side (went from empty to carrying traffic, or
            # the reverse) has no finite dB difference; a street silent on BOTH
            # sides has no level at all. Either way the street stays in the table
            # with d_db = NaN so its NO2 column survives (audit finding 4: the old
            # `continue` silently deleted the whole street, NO2 numbers included,
            # if it was both-sides-silent in even one seed).
            d_db = (r.level_db_c - r.level_db_o
                    if np.isfinite(r.level_db_o) and np.isfinite(r.level_db_c)
                    else np.nan)
            per_seed.setdefault(nm, []).append(
                (r.no2_g_c - r.no2_g_o, r.no2_g_o, d_db))
        used += 1
    return per_seed, used


def verdict(mean, sd, n, signs):
    """The campaign's pre-set bar, unchanged: unanimous sign AND |t| > 3."""
    unanimous = signs == n or signs == 0
    t = abs(mean) / (sd / np.sqrt(n)) if sd > 0 else float("inf")
    return ("SUPPORTED" if unanimous and t > 3
            else "weak" if unanimous else "NOT SUPPORTED"), t


def report(near_km=NEAR_KM):
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    geo = load_geo(G)

    for arm in ARMS:
        per_seed, used = collect(arm, geo, near_km)
        print(f"\n{'=' * 88}\n{arm.upper()}: NO2 vs NOISE, near field "
              f"(<={near_km:.0f} km), {used} paired seeds\n{'=' * 88}")
        if used < 2:
            print("  need at least 2 paired seeds")
            continue

        rows = []
        for nm, v in per_seed.items():
            if len(v) != used:
                continue
            dg = np.array([x[0] for x in v])
            base = np.array([x[1] for x in v])
            ddb = np.array([x[2] for x in v])
            finite = ddb[np.isfinite(ddb)]
            rows.append((nm, dg, base, ddb, finite))

        hdr = (f"{'street':30s} {'dNO2 g':>9s} {'NO2 verdict':>14s} "
               f"{'dNoise dB':>10s} {'noise verdict':>14s} {'seeds':>6s}")
        print(hdr)
        print("-" * len(hdr))
        supported = {}          # street -> (no2 supported?, noise supported?)
        for nm, dg, base, ddb, finite in rows:
            n = len(dg)
            vg, _ = verdict(dg.mean(), dg.std(ddof=1) if n > 1 else 0.0,
                            n, int((dg > 0).sum()))
            # The noise verdict requires a finite dB change in EVERY seed (audit
            # finding 3: the pre-set bar's unanimity p-value assumes the full seed
            # set; unanimity over a quiet subset would inherit the SUPPORTED stamp
            # with none of its evidential weight). Partial coverage reports the
            # on/off pattern instead of a verdict.
            if len(finite) == n:
                vn, _ = verdict(finite.mean(), finite.std(ddof=1),
                                len(finite), int((finite > 0).sum()))
            else:
                vn = f"on/off {len(finite)}/{n}"
            supported[nm] = (vg == "SUPPORTED", vn == "SUPPORTED")

        for nm, dg, base, ddb, finite in sorted(rows, key=lambda r: -abs(r[1].mean()))[:12]:
            n = len(dg)
            vg, _ = verdict(dg.mean(), dg.std(ddof=1) if n > 1 else 0.0,
                            n, int((dg > 0).sum()))
            if len(finite) == n:
                vn, _ = verdict(finite.mean(), finite.std(ddof=1),
                                len(finite), int((finite > 0).sum()))
                nz = f"{finite.mean():+10.2f}"
            else:
                vn = f"on/off {len(finite)}/{n}"
                nz = f"{finite.mean():+10.2f}" if len(finite) else "     n/a"
            print(f"{nm[:30]:30s} {dg.mean():+9.1f} {vg:>14s} "
                  f"{nz} {vn:>14s} {len(finite):3d}/{n:<2d}")

        # the actual question: does the ranking differ between the two surfaces?
        ranked = [(nm, dg.mean(), (fin.mean() if len(fin) == len(dg) else np.nan))
                  for nm, dg, base, ddb, fin in rows]
        ranked = [r for r in ranked if np.isfinite(r[2])]
        if len(ranked) >= 3:
            from scipy.stats import spearmanr
            by_no2 = [r[0] for r in sorted(ranked, key=lambda r: -r[1])]
            by_db = [r[0] for r in sorted(ranked, key=lambda r: -r[2])]
            rho = spearmanr([r[1] for r in ranked], [r[2] for r in ranked]).statistic
            print(f"\n  streets ranked by NO2 gain : {', '.join(by_no2[:5])}")
            print(f"  streets ranked by dB gain  : {', '.join(by_db[:5])}")
            print(f"  rank agreement, all streets: Spearman {rho:+.3f} "
                  f"over {len(ranked)} streets")
            # Chaos is CORRELATED between the two surfaces (a street that randomly
            # drew more cars gains both grams and dB), so the all-streets rho mixes
            # physics with chaos agreement (audit finding 5). The subset that passed
            # the bar on either surface is the physics-only version.
            sup = [r for r in ranked if any(supported.get(r[0], (False, False)))]
            if len(sup) >= 3:
                rho_s = spearmanr([r[1] for r in sup],
                                  [r[2] for r in sup]).statistic
                print(f"  rank agreement, SUPPORTED-only: Spearman {rho_s:+.3f} "
                      f"over {len(sup)} streets")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="check the vectorized CNOSSOS against noise.py, then exit")
    ap.add_argument("--near-km", type=float, default=NEAR_KM)
    a = ap.parse_args()
    if a.verify:
        raise SystemExit(0 if verify_vectorized() else 1)
    if not verify_vectorized():
        raise SystemExit("vectorized CNOSSOS disagrees with noise.py; refusing to run")
    report(a.near_km)


if __name__ == "__main__":
    main()
