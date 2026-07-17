"""EXPLORATORY (branch experiment/decay): EVALUATION ONLY of the decay-fit run.

Compares the LODES-fitted-decay run (powell_through_decayfit, scale 1082 m) against
the powell_through reference run (scale 1500 m, everything else identical) on:

  (a) the traffic-count rank correlation vs the held-out PBOT counts, using
      validate_traffic.py's corrected segment-geometry snapping. This is an
      EVALUATION METRIC ONLY: the decay scale was chosen from the LODES commute
      flows, never from these counts, so the counts remain a clean held-out test.
      Reporting the number does not make it a tuning target.

  (b) per-segment throughput agreement between the two runs (Spearman over all
      segments, and over segments either run actually used), which measures how
      sensitive the model's traffic surface is to this knob at all.

Reads saved run files only; runs no simulation.

Run it with:  python src/evaluate_decayfit.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import validate_traffic

REF_RUN = "powell_through"          # a-priori 1500 m decay (the committed reference)
FIT_RUN = "powell_through_decayfit"  # LODES-fitted 1082 m decay, same seed/demand


def _spearman(a, b):
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    # (a) held-out PBOT count validation for both runs (evaluation only, see docstring)
    print("=" * 72)
    print("(a) PBOT count validation, corrected geometry snapping (EVALUATION ONLY)")
    print("=" * 72)
    for run in (REF_RUN, FIT_RUN):
        print()
        validate_traffic.main(run)

    # (b) between-run surface agreement: does the model even care about this knob?
    print()
    print("=" * 72)
    print("(b) per-segment throughput agreement between the two runs")
    print("=" * 72)
    ref = pd.read_parquet(os.path.join(config.PROCESSED_DIR, f"{REF_RUN}_segments.parquet"))
    fit = pd.read_parquet(os.path.join(config.PROCESSED_DIR, f"{FIT_RUN}_segments.parquet"))
    m = ref.merge(fit, on=["u", "v", "key"], suffixes=("_ref", "_fit"))
    print(f"  {len(m)} segments matched between '{REF_RUN}' (1500 m) and "
          f"'{FIT_RUN}' (1082 m)")
    rho_all = _spearman(m["throughput_ref"], m["throughput_fit"])
    used = m[(m["throughput_ref"] > 0) | (m["throughput_fit"] > 0)]
    rho_used = _spearman(used["throughput_ref"], used["throughput_fit"])
    print(f"  throughput Spearman, all segments : {rho_all:+.3f}")
    print(f"  throughput Spearman, used segments: {rho_used:+.3f}  ({len(used)} segments)")
    rho_act = _spearman(m["value_ref"], m["value_fit"])
    print(f"  activity  Spearman, all segments : {rho_act:+.3f}")
    tot_r, tot_f = m["throughput_ref"].sum(), m["throughput_fit"].sum()
    print(f"  network totals: throughput {tot_r:,.0f} -> {tot_f:,.0f} "
          f"({100*(tot_f-tot_r)/tot_r:+.1f}%), "
          f"NOx {m['nox_g_ref'].sum():,.0f} g -> {m['nox_g_fit'].sum():,.0f} g "
          f"({100*(m['nox_g_fit'].sum()-m['nox_g_ref'].sum())/m['nox_g_ref'].sum():+.1f}%)")


if __name__ == "__main__":
    main()
