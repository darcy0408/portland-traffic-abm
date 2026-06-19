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


def idm_acceleration(v, gap, lead_v, v0,
                     a_max=config.IDM_A_MAX, b_comf=config.IDM_B_COMF,
                     T=config.IDM_T, s0=config.IDM_S0, delta=config.IDM_DELTA):
    """Intelligent Driver Model: how hard one car accelerates or brakes right now.

    This is the core of the whole simulation. It is a pure function: give it the
    car's situation, it returns an acceleration in m/s^2 (positive = speed up,
    negative = brake). It changes nothing and stores nothing, which makes it easy
    to test by eye.

    Arguments:
        v       current speed of this car (m/s)
        gap     clear distance to the back of the car ahead (m); use a large
                number or float('inf') when there is no car ahead
        lead_v  speed of the car ahead (m/s); ignored when there is no leader
        v0      this car's desired speed, i.e. the segment speed limit (m/s)

    The formula has two parts that pull against each other:

      free road:   a_max * (1 - (v/v0)**delta)
                   when v is well below v0 this is near a_max (accelerate);
                   as v approaches v0 it fades to zero (stop speeding up).

      interaction: -a_max * (s_star / gap)**2
                   s_star is the gap the driver *wants* given current speed and
                   how fast they are closing on the leader. If the real gap is
                   smaller than the wanted gap, this term grows and brakes hard.
    """
    # Floor the gap so an exact overlap can't divide by zero; treat it as bumper
    # contact, which the interaction term will then punish with heavy braking.
    gap = max(gap, 1e-3)

    # How fast we are closing on the leader (positive = catching up).
    delta_v = v - lead_v

    # The gap the driver *desires* right now: a standstill minimum (s0), plus a
    # speed-dependent following distance (v*T), plus an extra cushion that grows
    # when closing fast on the leader.
    s_star = s0 + max(0.0, v * T + (v * delta_v) / (2.0 * (a_max * b_comf) ** 0.5))

    free_term = 1.0 - (v / v0) ** delta
    interaction_term = (s_star / gap) ** 2
    return a_max * (free_term - interaction_term)


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
