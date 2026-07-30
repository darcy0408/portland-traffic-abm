"""Save and restore simulation state.

Checkpointing means a crash, a Colab disconnect, or a power outage never costs
more than CHECKPOINT_EVERY steps of work. The save writes to a temporary file
first and then renames it, so an interrupted write can never corrupt your only
checkpoint.

KNOWN LIMITATION (applies to every seeded stream). The state pickled here holds
the vehicles and the accumulated segment totals, NOT the RNG objects: the trip
stream (RANDOM_SEED), the signal stream (+1), the fleet stream (+2), and the
driver-heterogeneity stream (+3) are all rebuilt from the seed on resume, so a
resumed run is reproducible only as a whole, never step-identical to an
uninterrupted one past the first respawn. A related trap: a checkpoint written
with a per-vehicle flag (FLEET_MIXED, DRIVER_HETEROGENEITY) in the OTHER state
carries vehicles that lack the corresponding per-car draw, giving a mixed
population until every one of them respawns. Do not resume across a flag change
-- start a fresh RUN_NAME.
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
