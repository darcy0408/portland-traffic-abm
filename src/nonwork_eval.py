"""One-off evaluation run for the non-work (shopping/errand) demand layer.

Decides whether the B3 layer (config.DEMAND_NONWORK_ENABLED, commit f57c519)
earns the second pre-registered Rose Quarter arm reserved by the prereg's
model-variant clause: one metro run with the flag ON, scored afterward
against the held-out PBOT counts next to the flag-off baseline.

Design: byte-for-byte the same configuration as metrocal_base_n16500_s42
(metro_calibrated_experiment.run_one, arm "base": METRO overrides, all
realism flags off, mixed fleet, 16,500 vehicles, one simulated hour, seed
42) EXCEPT that DEMAND_NONWORK_ENABLED is True. That is achieved by
registering a "nonwork" arm holding only that flag and delegating to
run_one, so this file cannot drift from the experiment harness it must be
comparable to. run_one's arm-complement rule turns every realism flag off
because none of them appear in this arm, exactly as it does for "base".

    python src/nonwork_eval.py                # Orca: uses the cached metro graph
    python src/nonwork_eval.py --graph PATH   # explicit graph file

Output: metrocal_nonwork_n16500_s42_segments.parquet + _summary.json in
config.PROCESSED_DIR (skip-if-present, so resubmission is safe). Scoring
happens locally after harvest and is NOT part of this job.
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                  # noqa: E402
import metro_calibrated_experiment as mce      # noqa: E402

# the evaluation arm: base stack plus ONLY the non-work flag
mce.ARMS["nonwork"] = {"DEMAND_NONWORK_ENABLED": True}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--graph",
                    default=os.path.join(config.NETWORK_DIR, "graph.graphml"))
    args = ap.parse_args()
    job = {"arm": "nonwork", "seed": 42, "n_veh": 16500,
           "steps": mce.METRO["N_STEPS"],
           "name": "metrocal_nonwork_n16500_s42"}
    mce.run_one(job, args.graph)


if __name__ == "__main__":
    main()
