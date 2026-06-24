"""STAGE 2: VISUALIZE.

Reads the processed data file and produces figures. This script runs no
simulation. You can rerun it as often as you like, changing colors, axes, or
basemaps, without ever touching the expensive run that produced the data.

Run it with:  python src/visualize.py
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def load_segments():
    path = os.path.join(config.PROCESSED_DIR, f"{config.RUN_NAME}_segments.parquet")
    return pd.read_parquet(path)


def load_segments_named(run_name):
    """Load a specific run's results by name (used by the closure difference map,
    which needs both the '_open' and '_closed' result files)."""
    path = os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No results at {path}; run the closure experiment first "
                         f"(python src/generate.py closure).")
    return pd.read_parquet(path)


def load_network():
    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    return ox.load_graphml(graph_file)


def plot_network(G):
    """Plain street-network map, no simulation data needed.
    Use this to confirm the study area looks right before running the sim."""
    fig, ax = ox.plot_graph(
        G,
        edge_color="#3a76c4",
        edge_linewidth=0.7,
        node_size=0,
        bgcolor="white",
        show=False,
        close=False,
    )
    out = os.path.join(config.FIGURES_DIR, "network_map.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved network map to {out}")


def _segment_heatmap(G, vals, cbar_label, title, out_suffix, cmap_name="inferno"):
    """Shared heat-map renderer: color and thicken each segment by `vals`.

    The per-segment quantities are skewed (a few busy edges, many quiet ones), so
    we use a square-root color scale and clip the very top (98th percentile) so one
    or two edges don't wash out the rest. `vals` is one value per edge, aligned to
    G.edges(keys=True). Used for both the activity surface and the NO2 surface.
    """
    positive = vals[vals > 0]
    vmax = float(np.percentile(positive, 98)) if positive.size else 1.0
    norm = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=vmax)   # sqrt-ish scale
    cmap = mpl.colormaps[cmap_name]

    colors, widths = [], []
    for v in vals:
        if v <= 0:
            colors.append((0.16, 0.16, 0.20, 1.0))   # dim grey: street never used
            widths.append(0.4)
        else:
            t = norm(min(v, vmax))
            colors.append(cmap(t))
            widths.append(0.6 + 3.0 * t)             # busier segment -> thicker line

    bg = "#0e0e12"
    fig, ax = ox.plot_graph(
        G, edge_color=colors, edge_linewidth=widths, node_size=0,
        bgcolor=bg, show=False, close=False,
    )

    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    cbar.set_label(cbar_label, color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    ax.set_title(title, color="white")

    out = os.path.join(config.FIGURES_DIR, f"{config.RUN_NAME}_{out_suffix}.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    print(f"Saved figure to {out}")


def plot_segment_map(G, df):
    """Heat map of simulated traffic activity (vehicle-seconds) per street segment.
    Busy corridors light up; unused streets stay a dim grey."""
    value_by_edge = {(r.u, r.v, r.key): r.value for r in df.itertuples()}
    edges = list(G.edges(keys=True))
    vals = np.array([value_by_edge.get(e, 0.0) for e in edges])
    _segment_heatmap(
        G, vals,
        cbar_label="vehicle-seconds on segment",
        title=(f"Powell ABM: traffic activity per segment\n"
               f"{config.N_VEHICLES} vehicles, {config.N_STEPS} steps"),
        out_suffix="segment_map",
    )


def plot_no2_map(G, df):
    """Heat map of the modeled NO2 surface per street segment.

    The simulation stores NOx grams per segment (HBEFA3). The NO2 surface is
    NO2 = config.F_NO2 * NOx, applied here so the fraction can be retuned without
    rerunning the sim. This is the week-5 NO2 deliverable: the agent simulation's
    interaction dynamics (following, queueing, spillback) turned into emissions.
    """
    if "nox_g" not in df.columns:
        raise SystemExit("This run has no nox_g column; rerun generate.py to "
                         "produce the emission surface.")
    nox_by_edge = {(r.u, r.v, r.key): r.nox_g for r in df.itertuples()}
    edges = list(G.edges(keys=True))
    vals = config.F_NO2 * np.array([nox_by_edge.get(e, 0.0) for e in edges])
    _segment_heatmap(
        G, vals,
        cbar_label="NO2 (grams on segment)",
        title=(f"Powell ABM: modeled NO2 surface\n"
               f"{config.N_VEHICLES} vehicles, {config.N_STEPS} steps, "
               f"{config.EMISSION_CLASS}, f_NO2={config.F_NO2}"),
        out_suffix="no2_map",
        cmap_name="viridis",
    )


def plot_closure_diff(G):
    """Before/after closure map (Christof, Jun 23): where did NO2 move when the
    road closed? Differences the '_open' and '_closed' runs the closure experiment
    saved and colors each segment by NO2_closed - NO2_open.

      red  = NO2 went UP   (traffic diverted onto this street)
      blue = NO2 went DOWN (this street lost traffic, or fed the closed stretch)
      bright outline = the closed segments themselves

    This is the figure that shows what a static land-use model cannot: identical
    land use, but the pollution surface redistributes because the cars reroute.
    """
    from generate import closed_edges_in_zone   # shared so we agree on what's closed

    base = config.RUN_NAME
    open_df = load_segments_named(f"{base}_open")
    closed_df = load_segments_named(f"{base}_closed")
    open_nox = {(r.u, r.v, r.key): r.nox_g for r in open_df.itertuples()}
    closed_nox = {(r.u, r.v, r.key): r.nox_g for r in closed_df.itertuples()}
    closed_set = set(closed_edges_in_zone(G))

    edges = list(G.edges(keys=True))
    # NO2 change per segment; closed segments carry no through-traffic, so their
    # closed-run NO2 is absent from closed_nox and reads as 0 here.
    diffs = np.array([config.F_NO2 * (closed_nox.get(e, 0.0) - open_nox.get(e, 0.0))
                      for e in edges])

    # symmetric diverging scale, clipped at the 98th percentile of the change so a
    # single segment does not wash out the rest
    mag = np.abs(diffs[diffs != 0])
    vmax = float(np.percentile(mag, 98)) if mag.size else 1.0
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    cmap = mpl.colormaps["RdBu_r"]

    colors, widths = [], []
    for e, d in zip(edges, diffs):
        if e in closed_set:
            colors.append((1.0, 0.95, 0.3, 1.0))     # bright yellow: the closure
            widths.append(2.6)
        elif d == 0.0:
            colors.append((0.16, 0.16, 0.20, 1.0))   # dim grey: unchanged
            widths.append(0.4)
        else:
            colors.append(cmap(norm(np.clip(d, -vmax, vmax))))
            widths.append(0.6 + 3.0 * abs(norm(np.clip(d, -vmax, vmax)) - 0.5) * 2)

    bg = "#0e0e12"
    fig, ax = ox.plot_graph(
        G, edge_color=colors, edge_linewidth=widths, node_size=0,
        bgcolor=bg, show=False, close=False,
    )
    sm = mpl.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.6, pad=0.01)
    cbar.set_label("NO2 change, closed - open (g)  red = up, blue = down", color="white")
    cbar.ax.yaxis.set_tick_params(color="white")
    plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")
    ax.set_title(f"Powell ABM: closure effect on NO2\n"
                 f"{len(closed_set)} segments closed, traffic reroutes",
                 color="white")

    out = os.path.join(config.FIGURES_DIR, f"{base}_closure_diff.png")
    fig.savefig(out, dpi=200, bbox_inches="tight", facecolor=bg)
    plt.close(fig)
    print(f"Saved figure to {out}")


def _load_scenario(name):
    path = os.path.join(config.PROCESSED_DIR, f"scenario_{name}.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No trace at {path}; run the test-bench first "
                         f"(python src/scenarios.py).")
    return pd.read_parquet(path)


def plot_scenarios():
    """Turn the validation test-bench traces into one evidence sheet (Christof,
    Jun 24): four panels, each a small scenario whose outcome you can check by eye.
    This is the visual half of 'show me it works'; scenarios.py is the numeric half.

    The dashed reference lines mirror the constants in scenarios.py: the 50 km/h
    limit, the IDM desired gap, and the 0-30 s red phase.
    """
    one = _load_scenario("one_car")
    two = _load_scenario("two_cars")
    red = _load_scenario("red_light")

    L = config.VEHICLE_LENGTH_M
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    fig.suptitle("ABM validation: four hand-checkable scenarios", fontsize=14, weight="bold")

    # Panel A: one car accelerates to the limit and holds
    ax = axes[0, 0]
    v_limit = one["v"].max()                       # the car tops out exactly at v0
    ax.plot(one["t"], one["v"], color="#1f77b4", lw=2)
    ax.axhline(v_limit, ls="--", color="grey", lw=1)
    ax.text(one["t"].iloc[-1], v_limit, " speed limit", va="bottom", ha="right",
            color="grey", fontsize=9)
    ax.set_title("1) One car: accelerates to the limit, no overshoot")
    ax.set_xlabel("time (s)"); ax.set_ylabel("speed (m/s)")

    # Panel B: two cars, the clear gap settles to the IDM desired headway
    lead = two[two["id"] == 0].reset_index(drop=True)
    foll = two[two["id"] == 1].reset_index(drop=True)
    gap = lead["pos"].to_numpy() - L - foll["pos"].to_numpy()
    want = config.IDM_S0 + lead["v"].iloc[-1] * config.IDM_T
    ax = axes[0, 1]
    ax.plot(foll["t"], gap, color="#2ca02c", lw=2)
    ax.axhline(want, ls="--", color="grey", lw=1)
    ax.axhline(0, ls=":", color="red", lw=1)
    ax.text(foll["t"].iloc[-1], want, f" desired gap {want:.1f} m", va="bottom",
            ha="right", color="grey", fontsize=9)
    ax.set_title("2) Two cars: gap settles to the safe headway (never 0)")
    ax.set_xlabel("time (s)"); ax.set_ylabel("clear gap to leader (m)")

    # Panel C: two cars, the follower's speed converges to the leader's
    ax = axes[1, 0]
    ax.plot(lead["t"], lead["v"], color="#9467bd", lw=2, label="leader (slow)")
    ax.plot(foll["t"], foll["v"], color="#1f77b4", lw=2, label="follower")
    ax.set_title("3) Two cars: follower matches the leader's speed")
    ax.set_xlabel("time (s)"); ax.set_ylabel("speed (m/s)")
    ax.legend(loc="upper right", fontsize=9)

    # Panel D: one car at a red light stops short of the line, departs on green
    ax = axes[1, 1]
    car = red[red["id"] == 0]
    stop_line = car[car["idx"] == 0]["route_dist"].max() + config.IDM_S0   # halt point + s0
    ax.axvspan(0, 30, color="red", alpha=0.08)                      # red phase 0-30 s
    ax.text(15, car["route_dist"].max(), "red", color="red", ha="center", fontsize=9)
    ax.plot(car["t"], car["route_dist"], color="#d62728", lw=2)
    ax.axhline(stop_line, ls="--", color="grey", lw=1)
    ax.text(car["t"].iloc[-1], stop_line, " stop line", va="bottom", ha="right",
            color="grey", fontsize=9)
    ax.set_title("4) Red light: waits at the line, goes on green")
    ax.set_xlabel("time (s)"); ax.set_ylabel("distance along route (m)")

    for ax in axes.flat:
        ax.grid(True, alpha=0.25)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    out = os.path.join(config.FIGURES_DIR, "scenarios.png")
    fig.savefig(out, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved scenario evidence sheet to {out}")


if __name__ == "__main__":
    # `python src/visualize.py network`   draws just the street network.
    # `python src/visualize.py no2`       draws the modeled NO2 surface.
    # `python src/visualize.py closure`   draws the before/after closure surface.
    # `python src/visualize.py scenarios` draws the validation test-bench traces.
    # With no argument it draws the traffic-activity segment map.
    # All but `network` and `scenarios` need simulation output on disk.
    mode = sys.argv[1] if len(sys.argv) > 1 else "activity"
    if mode == "scenarios":
        plot_scenarios()                # reads scenario traces, needs no network
    else:
        G = load_network()
        if mode == "network":
            plot_network(G)
        elif mode == "no2":
            plot_no2_map(G, load_segments())
        elif mode == "closure":
            plot_closure_diff(G)
        else:
            plot_segment_map(G, load_segments())
