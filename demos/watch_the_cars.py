"""Watch the cars: the FULL model running with the lanes experiment ON.

Runs a fresh short simulation with every rule on (IDM car-following, signal
queueing, cross-edge spillback, gravity demand, 30% through-traffic, and this
worktree's virtual lanes, flipped on at runtime with no file edit), records
every car's position each second, and renders a two-view GIF: the whole
1.5 km network beside a zoomed stretch of SE Cesar Chavez between its
Gladstone and Holgate signals, where 2-lane flow and queue discharge are
visible.

Relationship to main's src/animate_cars.py (committed Jul 14, single-lane,
canonical): that one animates the committed base model; THIS one is the
lanes-on variant and lives with the experiment. The zoom is Chavez, not
Powell, because none of the 21 OSM-tagged signals touch a Powell edge in
this graph (in-model, cars traveling along Powell never stop at a red).

Governance: demo only. It runs its own small sim because saved runs store no
vehicle positions (a documented exception to figures-read-files); it uses no
checkpoints, touches no canonical data files, and writes only GIFs/PNGs into
outputs/demos/ (gitignored). Run: python demos/watch_the_cars.py
"""
import os
import sys
import math
import random
import time
import unicodedata
from collections import defaultdict

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, "src"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from shapely.geometry import LineString

import config
config.LANES_ENABLED = True          # demo only: runtime flip, nothing written

# Corridor configuration, forced at runtime (the mixed_rerun.py pattern; nothing
# is written to config.py). config.py's defaults are METRO scale -- 16,500
# vehicles over a 20 km radius -- while this demo animates the 1.5 km corridor
# graph, so taking the defaults would gridlock 16,500 cars on Powell and
# contradict the docstring above. These are the published corridor numbers.
config.N_VEHICLES = 500
config.STUDY_RADIUS_M = 1500
config.THROUGH_TRAFFIC_FRACTION = 0.30
config.DEMAND_GRAVITY = True
config.DEMAND_LODES_OD = False

import emissions
import generate as g

OUT = os.path.join(WT, "outputs", "demos")
WARMUP_S = 600                       # 10 sim-minutes to load the network
RECORD_S = 300                       # 5 sim-minutes recorded (one frame/second)

MOVING_C, STOPPED_C = "#2563eb", "#1e3a8a"   # same hue, darker = stopped
GREEN_C, RED_C = "#16a34a", "#dc2626"
INK, MUTED = "#374151", "#6b7280"


def main():
    os.makedirs(OUT, exist_ok=True)
    t_start = time.perf_counter()
    G = g.get_network()
    # get_network() returns whatever graph is cached, regardless of
    # STUDY_RADIUS_M, so the override above cannot by itself guarantee the
    # corridor. Fail loudly rather than animate 500 cars lost on a metro graph.
    if len(G.nodes) > 5000:
        raise SystemExit(
            f"cached graph has {len(G.nodes)} nodes: this is the metro graph, "
            "not the 1.5 km corridor this demo animates. Point NETWORK_DIR at "
            "the corridor cache (or delete it and let STUDY_RADIUS_M = 1500 "
            "redownload) before running.")
    g.prepare_network(G)
    signals = g.prepare_signals(G)
    lanes = {(u, v, k): d.get("n_lanes", 1)
             for u, v, k, d in G.edges(keys=True, data=True)}
    multi = sum(1 for n in lanes.values() if n > 1)
    print(f"network: {len(G.nodes)} nodes / {len(G.edges)} edges; "
          f"{len(signals['nodes'])} signals; {multi} multi-lane segments")

    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    coeffs = emissions.active_coeffs()
    demand = g.build_demand_weights(G, nodes)
    through = g.build_through_context(G, nodes)
    vehicles = [v for v in (g.make_vehicle(G, nodes, rng, vid, demand, through)
                            for vid in range(config.N_VEHICLES)) if v is not None]
    print(f"{len(vehicles)} vehicles spawned")

    # --- geometry: edge key -> (LineString in lon/lat, length_m, n_lanes) ----
    lat0 = float(np.mean([G.nodes[n]["y"] for n in G.nodes]))
    M_LAT = 1.0 / 111320.0                            # degrees per metre, north
    M_LON = 1.0 / (111320.0 * math.cos(math.radians(lat0)))
    geom = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        line = d.get("geometry")
        if line is None:
            line = LineString([(G.nodes[u]["x"], G.nodes[u]["y"]),
                               (G.nodes[v]["x"], G.nodes[v]["y"])])
        geom[(u, v, k)] = (line, float(d["length"]), d.get("n_lanes", 1))

    def car_xy(key, pos, lane):
        """Map (segment, metres-along, lane) to lon/lat. Cars sit on the RIGHT
        side of their direction of travel (like US driving), lanes stacked
        rightward; the offset is in real metres, converted to degrees."""
        line, L, _n = geom[key]
        f = min(max(pos / max(L, 1e-6), 0.0), 1.0)
        s = f * line.length
        p = line.interpolate(s)
        ds = max(line.length * 0.02, 1e-9)
        p1 = line.interpolate(max(s - ds, 0.0))
        p2 = line.interpolate(min(s + ds, line.length))
        dx_m = (p2.x - p1.x) / M_LON                  # travel direction, metres
        dy_m = (p2.y - p1.y) / M_LAT
        norm = math.hypot(dx_m, dy_m) or 1.0
        rx, ry = dy_m / norm, -dx_m / norm            # right-hand normal
        off = 4.0 + 5.0 * lane                        # metres right of centreline
        return p.x + rx * off * M_LON, p.y + ry * off * M_LAT

    # --- simulate: warm up unrecorded, then record one frame per second ------
    seg_tot, seg_nox, seg_thru = (defaultdict(float) for _ in range(3))
    frames = []
    for step in range(WARMUP_S + RECORD_S):
        g.step_vehicles(vehicles, config.DT, step * config.DT, seg_tot, seg_nox,
                        seg_thru, coeffs, G, nodes, rng, signals, demand,
                        through, lanes=lanes)
        if step < WARMUP_S:
            continue
        by_edge = defaultdict(list)
        for veh in vehicles:
            by_edge[veh["route"][veh["idx"]][:3]].append(veh)
        xs, ys, stop = [], [], []
        for key, grp in by_edge.items():
            grp.sort(key=lambda vv: vv["pos"])        # kernel order: rear first
            n_here = geom[key][2]
            for i, veh in enumerate(grp):
                x, y = car_xy(key, veh["pos"], i % n_here)
                xs.append(x)
                ys.append(y)
                stop.append(veh["v"] < 0.5)
        frames.append({"x": np.array(xs), "y": np.array(ys),
                       "stop": np.array(stop), "t": (step + 1) * config.DT})
    print(f"simulated {WARMUP_S + RECORD_S} s, recorded {len(frames)} frames "
          f"({time.perf_counter() - t_start:.1f} s so far)")

    # --- zoom window: SE Cesar Chavez between its two southern signals -------
    def plain(s):
        return unicodedata.normalize("NFKD", str(s)).encode(
            "ascii", "ignore").decode().lower()

    chavez_sigs = set()
    for u, v, k, d in G.edges(keys=True, data=True):
        if "chavez" in plain(d.get("name", "")):
            for node in (u, v):
                if node in signals["nodes"]:
                    chavez_sigs.add(node)
    pair = sorted(chavez_sigs, key=lambda n: float(G.nodes[n]["y"]))[:2]
    cx = float(np.mean([G.nodes[n]["x"] for n in pair]))
    cy = float(np.mean([G.nodes[n]["y"] for n in pair]))
    half_w, half_h = 170.0, 290.0                     # metres; tall N-S window
    zx0, zx1 = cx - half_w * M_LON, cx + half_w * M_LON
    zy0, zy1 = cy - half_h * M_LAT, cy + half_h * M_LAT
    zoom_sigs = [n for n in signals["nodes"]
                 if zx0 <= float(G.nodes[n]["x"]) <= zx1
                 and zy0 <= float(G.nodes[n]["y"]) <= zy1]
    print(f"zoom on Chavez nodes {pair}: {len(zoom_sigs)} signals in window")

    # --- figure ---------------------------------------------------------------
    fig, (axF, axZ) = plt.subplots(
        1, 2, figsize=(10.4, 5.4), dpi=100,
        gridspec_kw={"width_ratios": [1.6, 1.0]})
    fig.subplots_adjust(left=0.01, right=0.99, top=0.86, bottom=0.10, wspace=0.04)
    aspect = 1.0 / math.cos(math.radians(lat0))

    segs_all, lws_all = [], []
    for (u, v, k), (line, _L, n_l) in geom.items():
        segs_all.append(np.asarray(line.coords))
        lws_all.append(0.8 + 1.1 * (n_l - 1))
    for ax in (axF, axZ):
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect(aspect)
        for sp in ax.spines.values():
            sp.set_color("#e5e7eb")
    axF.add_collection(LineCollection(segs_all, colors="#d1d5db", linewidths=0.4))
    axZ.add_collection(LineCollection(segs_all, colors="#cbd5e1",
                                      linewidths=lws_all))
    xs_all = [float(G.nodes[n]["x"]) for n in G.nodes]
    ys_all = [float(G.nodes[n]["y"]) for n in G.nodes]
    axF.set_xlim(min(xs_all), max(xs_all))
    axF.set_ylim(min(ys_all), max(ys_all))
    axZ.set_xlim(zx0, zx1)
    axZ.set_ylim(zy0, zy1)
    axF.add_patch(Rectangle((zx0, zy0), zx1 - zx0, zy1 - zy0, fill=False,
                            edgecolor=INK, lw=1.0, zorder=5))
    axF.set_title(f"whole network, {len(vehicles)} cars", loc="left",
                  fontsize=10, color=INK)
    axZ.set_title("SE Cesar Chavez Blvd, Gladstone to Holgate\n"
                  "(thick street = 2 lanes)", loc="left", fontsize=10, color=INK)

    carsF = axF.scatter([], [], s=2.5, linewidths=0, zorder=4)
    carsZ = axZ.scatter([], [], s=26, linewidths=0.5, edgecolors="white", zorder=4)
    sig_x = [float(G.nodes[n]["x"]) for n in zoom_sigs]
    sig_y = [float(G.nodes[n]["y"]) for n in zoom_sigs]
    sigsZ = axZ.scatter(sig_x, sig_y, s=52, marker="s", linewidths=1.0,
                        edgecolors="white", zorder=6)
    clock = fig.text(0.01, 0.945, "", fontsize=11, color=INK)
    fig.text(0.99, 0.945, "dot = car (dark = stopped) · square = signal, "
             "green means Chavez's (N-S) direction flows", ha="right",
             fontsize=8.5, color=MUTED)
    fig.text(0.99, 0.015, "every rule on: car-following, signals, spillback, "
             "gravity demand, through-traffic, 2 virtual lanes on arterials",
             ha="right", fontsize=8, color=MUTED)

    def update(i):
        fr = frames[i]
        cols = np.where(fr["stop"], STOPPED_C, MOVING_C)
        carsF.set_offsets(np.column_stack([fr["x"], fr["y"]]))
        carsF.set_facecolors(cols)
        carsZ.set_offsets(np.column_stack([fr["x"], fr["y"]]))
        carsZ.set_facecolors(cols)
        # signal squares: green when the north-south phase (Chavez's) has green
        sigsZ.set_facecolors([GREEN_C if g.is_green(signals, n, 1, fr["t"])
                              else RED_C for n in zoom_sigs])
        mm, ss = divmod(int(fr["t"] - WARMUP_S), 60)
        clock.set_text(f"sim time {mm:02d}:{ss:02d}  (after 10 min warm-up)")
        return []

    def progress(cur, total):
        if cur % 60 == 0 or cur == total - 1:
            print(f"  rendering frame {cur + 1}/{total}")

    anim = FuncAnimation(fig, update, frames=len(frames), blit=False)
    gif = os.path.join(OUT, "watch_the_cars.gif")
    anim.save(gif, writer=PillowWriter(fps=12), progress_callback=progress)
    print("wrote", gif, f"({os.path.getsize(gif) / 1e6:.1f} MB)")
    print(f"total {time.perf_counter() - t_start:.1f} s")


if __name__ == "__main__":
    main()
