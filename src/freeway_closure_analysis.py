"""Where did the NO2 go when I-205 closed? Read-only readout of the campaign.

Differences each closed run against the shared open baseline and reports the
spatial redistribution, which is the whole claim: a static land-use surface
cannot move NO2 when a road shuts, because its land-use inputs do not change.

Reads only saved files (the three *_segments.parquet, the *_closed_edges.json,
and the cached graph for street names). Runs no simulation.

IMPORTANT, measured on this campaign: a microscopic model is chaotic under
perturbation. Closing 10 of 159,425 edges leaves ~50% of ALL segments slightly
different, at every distance from the closure out to 100 km, because delaying
some cars changes who meets whom everywhere downstream. Mean |change| is ~1.25 g
per segment within 1 km and flat at ~0.07-0.09 g from 2 km outward. So this
script reports the near field as the closure's footprint and the far field as
the noise floor it must beat. Do NOT cite network-wide "N segments changed" or a
sum of |change| over the whole network from a single seed: most of it is chaos.
Establishing a proper per-segment floor needs the same closure across several
seeds (compare src/closure_robustness.py, which does this for the Powell case).

    python src/freeway_closure_analysis.py
"""
import json
import os
import sys
from collections import defaultdict

import osmnx as ox
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config          # noqa: E402
import generate        # noqa: E402

BASE = "fw205"
SCENARIOS = ("abernethy", "powell")

# How far from the closure a change is still attributable to it. Set from this
# campaign's measured distance decay (signal ~14x the floor inside 1 km, at the
# floor by 2 km), NOT tuned to make a result look good.
NEAR_KM = 2.0


def _mid(G, e):
    u, v, _ = e
    return (0.5 * (float(G.nodes[u]["y"]) + float(G.nodes[v]["y"])),
            0.5 * (float(G.nodes[u]["x"]) + float(G.nodes[v]["x"])))


def load(run):
    p = os.path.join(config.PROCESSED_DIR, f"{run}_segments.parquet")
    df = pd.read_parquet(p).set_index(["u", "v", "key"])
    return df


def street_names(G):
    """(u, v, k) -> a readable street label, for grouping the movement by road."""
    out = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0] if nm else None
        if not nm:
            ref = d.get("ref")
            if isinstance(ref, list):
                ref = ref[0] if ref else None
            nm = ref
        cls = d.get("highway")
        if isinstance(cls, list):
            cls = cls[0] if cls else None
        out[(u, v, k)] = (str(nm) if nm else f"(unnamed {cls})", str(cls))
    return out


def main():
    print("loading the cached graph for street names ...")
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    names = street_names(G)

    open_df = load(f"{BASE}_open")
    f = config.F_NO2
    print(f"open baseline: {f * open_df.nox_g.sum():,.0f} g NO2 over "
          f"{len(open_df):,} directed segments "
          f"(F_NO2 = {f}, applied here not in the sim)\n")

    for scen in SCENARIOS:
        run = f"{BASE}_{scen}_closed"
        closed_df = load(run)
        with open(os.path.join(config.PROCESSED_DIR,
                               f"{run}_closed_edges.json")) as fh:
            rec = json.load(fh)
        closed_keys = {(u, v, k) for u, v, k in rec["removed"]}

        # align on the open baseline's index; closed runs are missing the
        # removed edges, which read as zero rather than as absent
        j = open_df.join(closed_df, how="left", lsuffix="_o", rsuffix="_c").fillna(0.0)
        j["d_nox"] = j.nox_g_c - j.nox_g_o
        j["d_thru"] = j.throughput_c - j.throughput_o

        tot_o = f * j.nox_g_o.sum()
        tot_c = f * j.nox_g_c.sum()
        print("=" * 74)
        print(f"{scen.upper()}  ({len(closed_keys)} edges closed)")
        print("=" * 74)
        print(f"network total NO2: {tot_o:,.0f} g -> {tot_c:,.0f} g "
              f"({100 * (tot_c - tot_o) / tot_o:+.1f}%)")

        # 1. the closed stretch itself: its NO2 goes to zero by construction
        on_closed = j[j.index.isin(closed_keys)]
        print(f"\nthe closed stretch: {f * on_closed.nox_g_o.sum():,.0f} g NO2 and "
              f"{on_closed.throughput_o.sum():,.0f} vehicle-crossings removed")

        # Distance from the closure, because the change is only interpretable
        # near it. MEASURED on this campaign: mean |change| per segment is
        # ~1.25 g within 1 km and flattens to ~0.07-0.09 g from 2 km all the way
        # out to 100 km, and the SHARE of segments that change at all is ~50% in
        # every distance band including the farthest. That flat floor is
        # microsimulation chaos, not redistribution: a closure delays some cars,
        # which changes who meets whom downstream, which jitters half the
        # network by a hair. Only the near field is a causal footprint. Reporting
        # network-wide "N segments changed" or summing |change| over everything
        # would be reporting the noise.
        moved = j[~j.index.isin(closed_keys)].copy()
        lats = [_mid(G, e)[0] for e in closed_keys if e in names]
        lons = [_mid(G, e)[1] for e in closed_keys if e in names]
        clat, clon = sum(lats) / len(lats), sum(lons) / len(lons)
        moved["km"] = [generate._haversine_m(clat, clon, *_mid(G, e)) / 1000.0
                       if e in names else float("nan") for e in moved.index]
        near = moved[moved.km <= NEAR_KM]
        far = moved[moved.km > NEAR_KM]
        floor = f * far.d_nox.abs().mean()
        print(f"\nnoise floor from the far field (>{NEAR_KM:.0f} km): "
              f"mean |change| {floor:.4f} g/segment over {len(far):,} segments")
        print(f"near field (<={NEAR_KM:.0f} km): mean |change| "
              f"{f * near.d_nox.abs().mean():.4f} g/segment "
              f"({f * near.d_nox.abs().mean() / floor:.0f}x the floor), "
              f"net {f * near.d_nox.sum():+,.1f} g over {len(near):,} segments")
        moved = near
        by_street = defaultdict(lambda: [0.0, 0.0, 0.0])   # d_nox, d_thru, base
        for idx, row in moved[moved.d_nox.abs() > 0].iterrows():
            nm, cls = names.get(idx, ("(unknown)", "?"))
            b = by_street[nm]
            b[0] += row.d_nox
            b[1] += row.d_thru
            b[2] += row.nox_g_o
        rows = [(nm, f * v[0], v[1], f * v[2]) for nm, v in by_street.items()]

        print("\ngainers (NO2 g, and % of that street's own baseline):")
        for nm, dn, dt, base in sorted(rows, key=lambda r: -r[1])[:12]:
            pct = f"{100 * dn / base:+.0f}%" if base > 0 else "new"
            print(f"   {nm[:44]:44s} {dn:+9.1f} g  {pct:>7s}  "
                  f"{dt:+9.0f} crossings")
        print("\nlosers:")
        for nm, dn, dt, base in sorted(rows, key=lambda r: r[1])[:8]:
            pct = f"{100 * dn / base:+.0f}%" if base > 0 else "n/a"
            print(f"   {nm[:44]:44s} {dn:+9.1f} g  {pct:>7s}  "
                  f"{dt:+9.0f} crossings")

        # 3. how concentrated is the near-field change
        changed = moved[moved.d_nox.abs() > 1e-9]
        up = changed[changed.d_nox > 0]
        print(f"\nwithin {NEAR_KM:.0f} km: {len(changed):,} of {len(moved):,} "
              f"segments changed; {len(up):,} up, {len(changed) - len(up):,} down")
        print(f"   NO2 gained on rising near-field segments: "
              f"{f * up.d_nox.sum():,.0f} g")

        # 4. did the OTHER freeway take the load? the interesting systems answer.
        # Freeway mainlines are evaluated network-wide on purpose: a diverted
        # trip rejoins I-5 far from the closure, so this one is a routing
        # question, not a near-field question. Treat it as suggestive until the
        # multi-seed floor is measured (see the header note).
        for other in ("I 5", "I 205", "OR 99E", "OR 213"):
            keys = [e for e in generate.freeway_mainline_edges(G, other)
                    if e in j.index and e not in closed_keys]
            moved_all = j[~j.index.isin(closed_keys)]
            if not keys:
                continue
            sub = moved_all.loc[keys]
            d = f * sub.d_nox.sum()
            b = f * sub.nox_g_o.sum()
            print(f"   {other:7s} mainline: {d:+8.1f} g "
                  f"({100 * d / b if b else 0:+.1f}% of its {b:,.0f} g)")
        print()


if __name__ == "__main__":
    main()
