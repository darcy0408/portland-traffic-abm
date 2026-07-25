"""Realism showcase: the FULL model with every experiment-branch feature ON.

Runs a fresh short simulation with the base rules (IDM car-following, signal
queueing, cross-edge spillback, gravity demand, 30% through-traffic) PLUS all
three realism features from this worktree, flipped on at runtime with no file
edit: MOBIL explicit-lane changing (Phase 3), per-driver IDM heterogeneity
(Phase 2), and Webster per-node signal timing measured from this model's own
flows (Phase 4). Records every car's position each second and renders TWO
separate GIFs: the whole 1.5 km network, and a zoom on SE Cesar Chavez Blvd
between its Gladstone and Holgate signals, where 2-lane flow, lane changes,
and Webster's asymmetric green (plus its all-red clearance) are all visible
in one frame.

Relationship to demos/watch_the_cars.py (lanes-only variant, same worktree):
that one shows Phase 1's frictionless VIRTUAL lanes in isolation. This one is
its successor for the progress-report slide -- MOBIL's real lane identity
(veh["lane"], paid for with a genuine gap search) plus heterogeneity and
Webster timing on top, all four Phase 2-4 features stacked. LANES_ENABLED
stays False throughout: it is a different, mutually exclusive model of the
same lanes (see generate.build_mobil_context's refusal), and MOBIL is the one
this demo is built to show off.

Governance: demo only, same discipline as watch_the_cars.py. It runs its own
small sim because saved runs store no vehicle positions (the documented
exception to figures-read-files); no checkpoints, no writes under data/
anywhere, and it writes only GIFs into outputs/demos/ (gitignored). This is
the only simulation running on this machine while it runs. Run:
    python demos/realism_showcase.py
"""
import os
import sys
import json
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
import matplotlib.colors as mcolors
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from shapely.geometry import LineString
from PIL import Image, ImageSequence

import config
# Demo-only runtime flips -- nothing written to config.py. Every realism
# feature this worktree built goes on at once; LANES_ENABLED is left at its
# default False because it is a DIFFERENT (frictionless, virtual) model of
# lanes and mutually exclusive with MOBIL (build_mobil_context refuses both).
config.DRIVER_HETEROGENEITY = True
config.MOBIL_ENABLED = True
config.WEBSTER_ENABLED = True

# Corridor configuration, forced at runtime (same pattern and same numbers as
# watch_the_cars.py / mixed_rerun.py). config.py's checked-in defaults are
# METRO scale (16,500 vehicles, 20 km radius); this demo animates the 1.5 km
# corridor graph, so taking the defaults would gridlock the network and
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
RING_FRAMES = 2                      # ~2 s: how long a lane-change ring lingers

MOVING_C, STOPPED_C = "#2563eb", "#1e3a8a"   # same hue, darker = stopped
GREEN_C, RED_C, AMBER_C = "#16a34a", "#dc2626", "#f59e0b"
INK, MUTED = "#374151", "#6b7280"


def load_measured_flows():
    """The Webster payoff run's measured approach flows (data/processed/
    realism_webster_plans.json, key 'flows_veh_h', "u|v|k" string keys). Passing
    these into generate.prepare_signals(G, flows=...) reproduces the EXACT
    per-node Webster plans (cycle + split) that authoritative run used, rather
    than re-running this demo's own short warmup measurement -- the plan is a
    pure function of the flows plus config.WEBSTER_* (unchanged since), so this
    is reproduction, not a shortcut that changes the numbers."""
    path = os.path.join(WT, "data", "processed", "realism_webster_plans.json")
    with open(path) as f:
        plan = json.load(f)
    flows = {}
    for key_str, veh_h in plan["flows_veh_h"].items():
        u_s, v_s, k_s = key_str.split("|")
        flows[(int(u_s), int(v_s), int(k_s))] = veh_h
    print(f"loaded {len(flows)} measured approach flows from "
          f"{os.path.basename(path)} (run {plan['run']!r}, seed {plan['seed']})")
    return flows


def shrink_gif(path, colors=48, n_ref_frames=24, protect_hex=()):
    """Re-palette an already-written GIF to a small SHARED colour table and
    re-save with Pillow's optimizer. Pure image compression -- fewer colour
    bins, same pixels otherwise -- done because matplotlib/Pillow's default
    GIF writer gives each frame its own adaptive palette, which bloats a
    many-frame animation several times over for no visual gain at this size.

    The shared palette is built from a COLLAGE of several frames spread across
    the recorded window, not just one: a single reference frame can miss a
    state that matters here (the signal's amber all-red clearance is only a
    few frames wide out of 300). Even that was not enough on its own: the
    signal squares are a handful of small, anti-aliased marker pixels among
    many more background/edge-blend shades, so plain MEDIANCUT quantization
    of real frames spent its colour budget on those blends and merged
    GREEN_C/RED_C/AMBER_C into one indistinguishable muddy brown (verified by
    sampling the rendered pixels before this fix). `protect_hex` pastes a
    solid block of each colour that MUST survive (the signal and car palette)
    into the collage before quantizing, so MEDIANCUT is forced to give each
    one its own bin regardless of how few real pixels it covers.
    Overwrites `path` in place; prints the size before and after."""
    before = os.path.getsize(path) / 1e6
    im = Image.open(path)
    duration = im.info.get("duration", 83)
    raw = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
    step = max(1, len(raw) // n_ref_frames)
    sample = raw[::step]
    w, h = sample[0].size
    swatch_h = 24
    collage = Image.new("RGB", (w, h * len(sample) + swatch_h * len(protect_hex)))
    for i, fr in enumerate(sample):
        collage.paste(fr, (0, i * h))
    for j, hexcol in enumerate(protect_hex):
        block = Image.new("RGB", (w, swatch_h), mcolors.to_hex(hexcol))
        collage.paste(block, (0, h * len(sample) + j * swatch_h))
    ref = collage.quantize(colors=colors, method=Image.MEDIANCUT)
    frames = [f.quantize(palette=ref, dither=Image.Dither.FLOYDSTEINBERG)
              for f in raw]
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, optimize=True)
    after = os.path.getsize(path) / 1e6
    print(f"  shrank {os.path.basename(path)}: {before:.2f} MB -> {after:.2f} MB")


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
    flows = load_measured_flows()
    signals = g.prepare_signals(G, flows=flows)
    n_with_plan = sum(1 for n in signals["nodes"] if signals["node_cycle"].get(n))
    lanes = {(u, v, k): d.get("n_lanes", 1)
             for u, v, k, d in G.edges(keys=True, data=True)}
    multi = sum(1 for n in lanes.values() if n > 1)
    print(f"network: {len(G.nodes)} nodes / {len(G.edges)} edges; "
          f"{len(signals['nodes'])} signals ({n_with_plan} with a Webster plan); "
          f"{multi} multi-lane segments")

    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    coeffs = emissions.active_coeffs()
    driver_ctx = g.build_driver_context()
    mobil_ctx = g.build_mobil_context(G)
    demand = g.build_demand_weights(G, nodes)
    through = g.build_through_context(G, nodes)
    vehicles = [v for v in (g.make_vehicle(G, nodes, rng, vid, demand, through,
                                           driver_ctx=driver_ctx)
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
        rightward; the offset is in real metres, converted to degrees. `lane`
        is the car's REAL integer lane index (veh["lane"], MOBIL's explicit
        lane identity) -- not a virtual queue-rank trick -- clamped defensively
        in case a checkpoint or a narrowing segment left it stale."""
        line, L, n_l = geom[key]
        lane = min(max(lane, 0), max(n_l - 1, 0))
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
    # Lane-change detection: track each vehicle's (edge, lane) between steps.
    # SAME edge + DIFFERENT lane than last step = a MOBIL mid-segment change
    # (as opposed to the lane re-clamp that happens on crossing into a new
    # segment, which always changes the edge too and so is correctly excluded).
    # Tracked from step 0 (through the warmup) so the first RECORDED frame has
    # real history to compare against, not a spurious first-frame "change".
    seg_tot, seg_nox, seg_thru = (defaultdict(float) for _ in range(3))
    prev_state = {}          # vid -> (edge_key, lane) as of the last step
    changed_prev_step = set()
    total_lane_changes = 0
    frames = []
    for step in range(WARMUP_S + RECORD_S):
        g.step_vehicles(vehicles, config.DT, step * config.DT, seg_tot, seg_nox,
                        seg_thru, coeffs, G, nodes, rng, signals, demand,
                        through, driver_ctx=driver_ctx, mobil_ctx=mobil_ctx)

        changed_this_step = set()
        for veh in vehicles:
            vid = veh["id"]
            edge_key = veh["route"][veh["idx"]][:3]
            lane = veh.get("lane", 0)
            prev = prev_state.get(vid)
            if prev is not None and prev[0] == edge_key and prev[1] != lane:
                changed_this_step.add(vid)
                if step >= WARMUP_S:
                    total_lane_changes += 1
            prev_state[vid] = (edge_key, lane)

        if step < WARMUP_S:
            changed_prev_step = changed_this_step
            continue

        ring_ids = changed_this_step | changed_prev_step   # ~2 s of ring
        changed_prev_step = changed_this_step

        xs, ys, stop, ring = [], [], [], []
        for veh in vehicles:
            key = veh["route"][veh["idx"]][:3]
            x, y = car_xy(key, veh["pos"], veh.get("lane", 0))
            xs.append(x)
            ys.append(y)
            stop.append(veh["v"] < 0.5)
            ring.append(veh["id"] in ring_ids)
        frames.append({"x": np.array(xs), "y": np.array(ys),
                       "stop": np.array(stop), "ring": np.array(ring),
                       "t": (step + 1) * config.DT})
    print(f"simulated {WARMUP_S + RECORD_S} s, recorded {len(frames)} frames, "
          f"{total_lane_changes} lane changes in the recorded window "
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
    for n in pair:
        c = signals["node_cycle"].get(n)
        s = signals["node_split"].get(n)
        if c is not None:
            print(f"  Chavez signal {n}: cycle {c:.1f}s, NS split "
                  f"{1 - s:.3f} (EW split {s:.3f})")
    print(f"zoom on Chavez nodes {pair}: {len(zoom_sigs)} signals in window")

    # --- figure ---------------------------------------------------------------
    aspect = 1.0 / math.cos(math.radians(lat0))
    xs_all = [float(G.nodes[n]["x"]) for n in G.nodes]
    ys_all = [float(G.nodes[n]["y"]) for n in G.nodes]
    segs_all, lws_all = [], []
    for (u, v, k), (line, _L, n_l) in geom.items():
        segs_all.append(np.asarray(line.coords))
        lws_all.append(0.8 + 1.1 * (n_l - 1))

    caption_on = ("every realism feature on: 2-lane streets, MOBIL lane "
                  "changing, per-driver variation, Webster signal timing "
                  "measured from the model's own flows")

    # === GIF 1: the whole network =========================================
    # Compact on purpose (target < 4 MB): small figsize/dpi first, then a
    # shared-palette re-encode below (shrink_gif) does the rest.
    figF, axF = plt.subplots(figsize=(4.6, 4.6), dpi=90)
    figF.subplots_adjust(left=0.02, right=0.98, top=0.88, bottom=0.10)
    axF.set_xticks([])
    axF.set_yticks([])
    axF.set_aspect(aspect)
    for sp in axF.spines.values():
        sp.set_color("#e5e7eb")
    axF.add_collection(LineCollection(segs_all, colors="#d1d5db", linewidths=0.4))
    axF.set_xlim(min(xs_all), max(xs_all))
    axF.set_ylim(min(ys_all), max(ys_all))
    axF.add_patch(Rectangle((zx0, zy0), zx1 - zx0, zy1 - zy0, fill=False,
                            edgecolor=INK, lw=1.0, zorder=5))
    axF.set_title(f"whole 1.5 km network, {len(vehicles)} cars", loc="left",
                  fontsize=10, color=INK)
    carsF = axF.scatter([], [], s=2.5, linewidths=0, zorder=4)
    clockF = figF.text(0.02, 0.945, "", fontsize=11, color=INK)
    figF.text(0.98, 0.015, caption_on, ha="right", fontsize=7.5, color=MUTED,
              wrap=True)

    def update_full(i):
        fr = frames[i]
        cols = np.where(fr["stop"], STOPPED_C, MOVING_C)
        carsF.set_offsets(np.column_stack([fr["x"], fr["y"]]))
        carsF.set_facecolors(cols)
        mm, ss = divmod(int(fr["t"] - WARMUP_S), 60)
        clockF.set_text(f"sim time {mm:02d}:{ss:02d}  (after 10 min warm-up)")
        return []

    def progress(cur, total, label):
        if cur % 60 == 0 or cur == total - 1:
            print(f"  rendering {label} frame {cur + 1}/{total}")

    animF = FuncAnimation(figF, update_full, frames=len(frames), blit=False)
    gif_full = os.path.join(OUT, "realism_full.gif")
    animF.save(gif_full, writer=PillowWriter(fps=12),
               progress_callback=lambda c, t: progress(c, t, "full"))
    plt.close(figF)
    print(f"wrote {gif_full} ({os.path.getsize(gif_full) / 1e6:.2f} MB)")
    shrink_gif(gif_full, colors=48,
               protect_hex=[MOVING_C, STOPPED_C, "white", INK, MUTED])

    # === GIF 2: the Chavez zoom -- the star ================================
    figZ, axZ = plt.subplots(figsize=(4.6, 5.4), dpi=100)
    figZ.subplots_adjust(left=0.02, right=0.98, top=0.86, bottom=0.12)
    axZ.set_xticks([])
    axZ.set_yticks([])
    axZ.set_aspect(aspect)
    for sp in axZ.spines.values():
        sp.set_color("#e5e7eb")
    axZ.add_collection(LineCollection(segs_all, colors="#cbd5e1", linewidths=lws_all))
    axZ.set_xlim(zx0, zx1)
    axZ.set_ylim(zy0, zy1)
    axZ.set_title("SE Cesar Chavez Blvd, Gladstone to Holgate\n"
                  "(thick street = 2 lanes)", loc="left", fontsize=10, color=INK)

    carsZ = axZ.scatter([], [], s=26, linewidths=0.5, edgecolors="white", zorder=4)
    # lane-change ring: a hollow white circle drawn OVER a car for ~2 s right
    # after generate._mobil_lane_pass moves it into a new lane. The axes
    # background is white (matching watch_the_cars.py's palette exactly), so a
    # plain white ring would be invisible everywhere except over a road line;
    # a slightly larger dark "halo" ring drawn first, with the white ring on
    # top, keeps the white ring visible against ANY of this figure's colours.
    ringZ_halo = axZ.scatter([], [], s=150, marker="o", facecolors="none",
                             edgecolors=INK, linewidths=3.2, zorder=5)
    ringZ = axZ.scatter([], [], s=150, marker="o", facecolors="none",
                        edgecolors="white", linewidths=1.6, zorder=5.5)
    sig_x = [float(G.nodes[n]["x"]) for n in zoom_sigs]
    sig_y = [float(G.nodes[n]["y"]) for n in zoom_sigs]
    sigsZ = axZ.scatter(sig_x, sig_y, s=52, marker="s", linewidths=1.0,
                        edgecolors="white", zorder=6)
    # clock short and left; legend two EXPLICIT lines right-aligned, so the two
    # can never span into each other (the first cut had them colliding)
    clockZ = figZ.text(0.02, 0.955, "", fontsize=10, color=INK)
    figZ.text(0.98, 0.985, "dot = car (dark = stopped) · ring = lane change\n"
              "square = N-S signal: green/red = phase, amber = clearance",
              ha="right", va="top", fontsize=7, color=MUTED)
    lane_change_note = (f" ({total_lane_changes} lane changes in these "
                        f"5 minutes)" if total_lane_changes else "")
    figZ.text(0.98, 0.015, caption_on + lane_change_note +
              "; recorded after a 10 min warm-up", ha="right",
              fontsize=7.5, color=MUTED, wrap=True)

    def update_zoom(i):
        fr = frames[i]
        cols = np.where(fr["stop"], STOPPED_C, MOVING_C)
        carsZ.set_offsets(np.column_stack([fr["x"], fr["y"]]))
        carsZ.set_facecolors(cols)
        if fr["ring"].any():
            ring_xy = np.column_stack([fr["x"][fr["ring"]], fr["y"][fr["ring"]]])
        else:
            ring_xy = np.empty((0, 2))
        ringZ.set_offsets(ring_xy)
        ringZ_halo.set_offsets(ring_xy)
        # signal squares: green = Chavez's (N-S, phase 1) own green; red = the
        # other (EW) phase has it instead; amber = neither -- the Webster
        # yellow+all-red clearance, real and worth showing (not a rendering
        # artifact: is_green returns False for BOTH phases during it).
        sig_colors = []
        for n in zoom_sigs:
            green_ns = g.is_green(signals, n, 1, fr["t"])
            green_ew = g.is_green(signals, n, 0, fr["t"])
            if green_ns:
                sig_colors.append(GREEN_C)
            elif green_ew:
                sig_colors.append(RED_C)
            else:
                sig_colors.append(AMBER_C)
        sigsZ.set_facecolors(sig_colors)
        mm, ss = divmod(int(fr["t"] - WARMUP_S), 60)
        clockZ.set_text(f"sim time {mm:02d}:{ss:02d}")
        return []

    animZ = FuncAnimation(figZ, update_zoom, frames=len(frames), blit=False)
    gif_zoom = os.path.join(OUT, "realism_zoom.gif")
    animZ.save(gif_zoom, writer=PillowWriter(fps=12),
               progress_callback=lambda c, t: progress(c, t, "zoom"))
    plt.close(figZ)
    print(f"wrote {gif_zoom} ({os.path.getsize(gif_zoom) / 1e6:.2f} MB)")
    shrink_gif(gif_zoom, colors=64,   # more colours: this one is the star
               protect_hex=[MOVING_C, STOPPED_C, GREEN_C, RED_C, AMBER_C,
                            "white", INK, MUTED])
    print(f"total {time.perf_counter() - t_start:.1f} s")


if __name__ == "__main__":
    main()
