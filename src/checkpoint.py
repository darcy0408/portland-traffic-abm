"""Save and restore simulation state.

Checkpointing means a crash, a Colab disconnect, or a power outage never costs
more than CHECKPOINT_EVERY steps of work. The save writes to a temporary file
first and then renames it, so an interrupted write can never corrupt your only
checkpoint.

What is saved. The state pickled here holds the step counter, the vehicles, the
accumulated segment totals, a resume counter, and the internal state of every
seeded RNG stream the run loop consumes: the trip stream (RANDOM_SEED), the
fleet stream (+2) and the driver-heterogeneity stream (+3), captured by
run_simulation at the moment of each save. The signal stream (+1) and the
Webster warmup stream (+11) are fully consumed before the loop starts and
rebuild identically from the seed, so they need no saving. With the streams
restored, a resumed run is STEP-IDENTICAL to an uninterrupted one (the resume
scenario in src/scenarios.py checks this on every CI push). Until Oct 2026 the
streams were NOT saved and a resumed run was reproducible only as a whole; a
checkpoint from before then is refused on resume rather than silently rebuilt
from the seed. A related trap: a checkpoint written with a per-vehicle flag
(FLEET_MIXED, DRIVER_HETEROGENEITY) in the OTHER state carries vehicles that
lack the corresponding per-car draw, giving a mixed population until every one
of them respawns. Do not resume across a flag change -- start a fresh RUN_NAME.
"""
import os
import pickle


def checkpoint_path(raw_dir, run_name):
    return os.path.join(raw_dir, f"{run_name}_checkpoint.pkl")


def save_checkpoint(state, raw_dir, run_name):
    path = checkpoint_path(raw_dir, run_name)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        pickle.dump(state, f)
    os.replace(tmp, path)   # atomic: the real file is only ever a complete one


def load_checkpoint(raw_dir, run_name):
    path = checkpoint_path(raw_dir, run_name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return None   # no checkpoint yet, so start fresh
