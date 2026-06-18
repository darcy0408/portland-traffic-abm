"""STAGE 1: GENERATE DATA.

Runs the agent-based simulation and writes its results to disk. This script does
no plotting. Its only job is to produce data files that visualize.py reads later.
Keeping it plot-free is what lets you redraw any figure without rerunning the sim.

Run it with:  python src/generate.py
"""
import os
import sys
import random

import numpy as np
import pandas as pd
import osmnx as ox

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from checkpoint import save_checkpoint, load_checkpoint


def set_seeds(seed):
    random.seed(seed)
    np.random.seed(seed)


def get_network():
    """Download the street graph once, then reuse the cached copy.
    OSMnx downloads are slow, so we save the graph and load it on later runs."""
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    if os.path.exists(graph_file):
        return ox.load_graphml(graph_file)
    G = ox.graph_from_point(config.STUDY_CENTER, dist=config.STUDY_RADIUS_M,
                            network_type=config.NETWORK_TYPE)
    ox.save_graphml(G, graph_file)
    return G


def run_simulation(G):
    # Resume from a checkpoint if one exists, otherwise start at step 0.
    state = load_checkpoint(config.RAW_DIR, config.RUN_NAME)
    if state is None:
        # one accumulator per street segment; this is what you fill during the run
        segment_totals = {edge: 0.0 for edge in G.edges(keys=True)}
        state = {"step": 0, "segment_totals": segment_totals}
        # ---- initialise your vehicles here ----
    else:
        print(f"Resuming from step {state['step']}")

    segment_totals = state["segment_totals"]

    for step in range(state["step"], config.N_STEPS):
        # ================================================================
        # YOUR ABM STEP GOES HERE.
        # Move vehicles with car-following, handle signal queueing, then
        # add each vehicle's emission or noise contribution to the segment
        # it is on:  segment_totals[edge] += contribution
        # ================================================================

        state["step"] = step + 1
        if state["step"] % config.CHECKPOINT_EVERY == 0:
            save_checkpoint(state, config.RAW_DIR, config.RUN_NAME)
            print(f"Checkpoint saved at step {state['step']}")

    return segment_totals


def save_results(segment_totals):
    """Write final per-segment results as one tidy table.
    parquet keeps data types and stays compact. Switch to .to_csv if you ever
    want a file you can open and read by eye."""
    rows = [{"u": u, "v": v, "key": k, "value": val}
            for (u, v, k), val in segment_totals.items()]
    df = pd.DataFrame(rows)
    out = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    df.to_parquet(out)
    print(f"Saved {len(df)} segment results to {out}")


if __name__ == "__main__":
    set_seeds(config.RANDOM_SEED)
    G = get_network()
    totals = run_simulation(G)
    save_results(totals)
