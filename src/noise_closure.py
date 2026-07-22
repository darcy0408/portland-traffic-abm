"""Noise closure counterfactual: does the modeled noise surface shift when a
street closes? (Read-only: builds CNOSSOS surfaces from the SAVED open/closed
closure pair; runs no simulation.)

The NO2 closure result (Section 5 of the chapter) shows modeled NO2 stripped
from the closed corridor and moved onto the parallels. This script asks the same
question of the SECOND output surface: rebuild the per-segment dB(A) noise
surface for both halves of the saved closure pair and difference them.

Noise arithmetic is logarithmic, so the comparison is reported the way noise
should be: per-street LEVELS are the length-weighted energetic mean of segment
levels (sum of length * 10^(L/10), divided by total length, back to dB), and the
closure effect is the DIFFERENCE of those levels in dB, never a percent. For
scale: 3 dB is a doubling of acoustic energy; 10 dB reads roughly twice as loud.

Run:  python src/noise_closure.py [base_run]     (default powell_through)
Needs <base>_open_segments.parquet and <base>_closed_segments.parquet.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import noise

ARTERIALS = ["Powell", "Division", "Holgate"]
QUIET_FLOOR_DB = 0.0    # a segment with no flow has no traffic noise (NaN level)


def street_names():
    G = noise.load_network()
    _length, name = noise._edge_length_and_name(G)
    return name


def energetic_mean_db(levels_db, lengths_m):
    """Length-weighted energetic mean level over a set of segments, in dB(A).
    NaN levels (no flow) contribute zero acoustic energy but their length still
    counts, so a street going quiet pulls its mean level down rather than being
    dropped from the average."""
    w = np.asarray(lengths_m, float)
    L = np.asarray(levels_db, float)
    e = np.where(np.isfinite(L), 10.0 ** (L / 10.0), 0.0)
    if w.sum() <= 0:
        return np.nan
    mean_e = (w * e).sum() / w.sum()
    return 10.0 * np.log10(mean_e) if mean_e > 0 else np.nan


def main(base):
    names = street_names()
    surf = {}
    for half in ("open", "closed"):
        run = f"{base}_{half}"
        path = os.path.join(config.PROCESSED_DIR, f"{run}_segments.parquet")
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}; run the closure experiment first")
        s = noise.build_noise_surface(run)
        s["street"] = [names.get((r.u, r.v, r.key), "") for r in s.itertuples()]
        surf[half] = s
        flow = s["noise_db"].notna()
        print(f"[{half}] {flow.sum()} of {len(s)} segments carry flow; "
              f"dB(A) min {s['noise_db'].min():.1f} / "
              f"median {s['noise_db'].median():.1f} / max {s['noise_db'].max():.1f}")

    # outer merge so the 24 removed segments (open only) stay in the picture:
    # closed-side level NaN there means genuinely silent (street removed)
    o, c = surf["open"], surf["closed"]
    both = o.merge(c, on=["u", "v", "key"], how="outer",
                   suffixes=("_open", "_closed"))
    both["street"] = both["street_open"].fillna(both["street_closed"])
    both["length_m"] = both["length_m_open"].fillna(both["length_m_closed"])

    print(f"\nPer-arterial level (length-weighted energetic mean of segment dB(A), "
          f"receiver {noise.RECEIVER_DIST_M:.0f} m):")
    print(f"{'street':<12} {'open dB':>9} {'closed dB':>10} {'delta dB':>9}")
    for a in ARTERIALS:
        m = both["street"].str.contains(a, case=False, na=False)
        lo = energetic_mean_db(both.loc[m, "noise_db_open"], both.loc[m, "length_m"])
        lc = energetic_mean_db(both.loc[m, "noise_db_closed"], both.loc[m, "length_m"])
        print(f"{a:<12} {lo:>9.1f} {lc:>10.1f} {lc - lo:>+9.1f}")

    net_o = energetic_mean_db(both["noise_db_open"], both["length_m"])
    net_c = energetic_mean_db(both["noise_db_closed"], both["length_m"])
    print(f"{'NETWORK':<12} {net_o:>9.1f} {net_c:>10.1f} {net_c - net_o:>+9.1f}")

    # segment-level movement: how much of the map changes audibly? 3 dB is an
    # energy doubling; 1 dB is near the threshold of perceptible change.
    d = both["noise_db_closed"] - both["noise_db_open"]
    moved = d[np.isfinite(d)]
    silenced = both["noise_db_open"].notna() & both["noise_db_closed"].isna()
    awakened = both["noise_db_open"].isna() & both["noise_db_closed"].notna()
    print(f"\nSegment-level movement ({len(moved)} segments with flow in both halves):")
    for thr in (1.0, 3.0):
        print(f"  |delta| >= {thr:.0f} dB: {(moved.abs() >= thr).sum()} segments "
              f"({(moved >= thr).sum()} up, {(moved <= -thr).sum()} down)")
    print(f"  segments silenced by the closure (flow -> none): {int(silenced.sum())}")
    print(f"  segments newly loud (none -> flow):              {int(awakened.sum())}")

    # top street-level movers by delta of energetic mean level, min street length
    # so tiny fragments do not lead the table
    rows = []
    for street, grp in both[both["street"] != ""].groupby("street"):
        if grp["length_m"].sum() < 200:
            continue
        lo = energetic_mean_db(grp["noise_db_open"], grp["length_m"])
        lc = energetic_mean_db(grp["noise_db_closed"], grp["length_m"])
        if np.isfinite(lo) or np.isfinite(lc):
            rows.append((street, lo, lc,
                         (lc if np.isfinite(lc) else QUIET_FLOOR_DB)
                         - (lo if np.isfinite(lo) else QUIET_FLOOR_DB)))
    tbl = pd.DataFrame(rows, columns=["street", "open_db", "closed_db", "delta_db"])
    top = pd.concat([tbl.nsmallest(6, "delta_db"), tbl.nlargest(6, "delta_db")])
    print("\nlargest street-level movers (energetic mean dB(A), streets >= 200 m):")
    print(f"{'street':<38} {'open':>7} {'closed':>7} {'delta':>7}")
    for _, r in top.sort_values("delta_db").iterrows():
        print(f"{r['street']:<38} {r['open_db']:>7.1f} {r['closed_db']:>7.1f} "
              f"{r['delta_db']:>+7.1f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "powell_through")
