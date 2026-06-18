"""Save and restore simulation state.

Checkpointing means a crash, a Colab disconnect, or a power outage never costs
more than CHECKPOINT_EVERY steps of work. The save writes to a temporary file
first and then renames it, so an interrupted write can never corrupt your only
checkpoint.
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
