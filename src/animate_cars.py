"""CAR-DOT ANIMATION: watch the agents move (a demo asset, not a data product).

Renders the simulation as moving dots on the dark network: each dot is one
vehicle, colored by its current speed (red = stopped, green = free-flowing),
with the 21 real signalized intersections drawn as squares that flip red/green
as their east-west phase changes. Queues visibly form at red lights, release
on green, and spill back along the arterials, which is the car-interaction
story told directly.

This script is deliberately OUTSIDE the generate/visualize data pipeline:
- It runs its own SMALL simulation (the same kernel: make_vehicle,
  step_vehicles, prepare_signals) because the saved runs store per-segment
  totals, not per-vehicle positions, so an animation cannot be drawn from them.
- It writes NO data files and NO checkpoints. Its only outputs are GIFs in
  FIGURES_DIR. The authoritative runs in data/ are untouched.
- Seed, demand model, and through-traffic all come from config, so the traffic
  shown is the same model (powell_through settings) behind every cited number.

Usage:  python src/animate_cars.py
Writes: outputs/figures/cars_moving_full.gif  (whole network)
        outputs/figures/cars_moving_zoom.gif  (Powell & 26th close-up)
"""
import io
import math
import os
import random
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Rectangle
from PIL import Image
from shapely.geometry import LineString

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
import generate

# --- animation parameters (demo-only knobs, not simulation science) ---
WARMUP_S = 600      # simulate this long before recording, so queues are established
RECORD_S = 120      # seconds of movement captured (= frames at 1 fps recording)
FPS = 10            # playback frames per second: 10x real time, 12 s loop
DOT_VMAX = 13.4     # speed (m/s) mapped to the top of the color scale (30 mph)
ZOOM_HALF_LON = 0.0060   # zoom window half-width in degrees (~470 m at 45.5 N)
ZOOM_HALF_LAT = 0.0042   # zoom window half-height in degrees (~465 m)


def edge_geometries(G):
    """One shapely LineString per (u, v, key), in lon/lat degrees. OSMnx stores
    a geometry only for curved edges; straight ones are the node-to-node line."""
    geoms = {}
    for u, v, k, data in G.edges(keys=True, data=True):
        if "geometry" in data:
            geoms[(u, v, k)] = data["geometry"]
        else:
            geoms[(u, v, k)] = LineString([
                (G.nodes[u]["x"], G.nodes[u]["y"]),
                (G.nodes[v]["x"], G.nodes[v]["y"]),
            ])
    return geoms


def vehicle_xy(veh, geoms):
    """Current (lon, lat) of one vehicle: fraction along its edge's length
    attribute, interpolated along that edge's real street geometry."""
    edge = veh["route"][veh["idx"]]
    geom = geoms[edge[:3]]
    frac = min(max(edge[3] and veh["pos"] / edge[3], 0.0), 1.0)
    pt = geom.interpolate(frac * geom.length)
    return pt.x, pt.y


def record(G):
    """Run the sim (warmup + recorded window) and capture, per recorded second:
    every vehicle's (x, y, speed) and every signal's east-west green state."""
    generate.prepare_network(G)
    signals = generate.prepare_signals(G)
    geoms = edge_geometries(G)
    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    nox_coeffs = generate.emissions.active_coeffs()
    demand = generate.build_demand_weights(G, nodes)
    through = generate.build_through_context(G, nodes)

    vehicles = []
    for vid in range(config.N_VEHICLES):
        veh = generate.make_vehicle(G, nodes, rng, vid, demand, through)
        if veh is not None:
            vehicles.append(veh)

    # throwaway accumulators: step_vehicles needs them, nothing reads them
    seg_tot = {e: 0.0 for e in G.edges(keys=True)}
    seg_nox = {e: 0.0 for e in G.edges(keys=True)}
    seg_thr = {e: 0.0 for e in G.edges(keys=True)}

    sig_nodes = sorted(signals["nodes"])
    sig_xy = np.array([(G.nodes[n]["x"], G.nodes[n]["y"]) for n in sig_nodes])

    frames = []
    t0 = time.perf_counter()
    total = WARMUP_S + RECORD_S
    for step in range(total):
        t = step * config.DT
        generate.step_vehicles(vehicles, config.DT, t, seg_tot, seg_nox, seg_thr,
                               nox_coeffs, G, nodes, rng, signals, demand, through)
        if step >= WARMUP_S:
            xy = np.array([vehicle_xy(v, geoms) for v in vehicles])
            spd = np.array([v["v"] for v in vehicles])
            green_ew = np.array([generate.is_green(signals, n, 0, t)
                                 for n in sig_nodes])
            frames.append((xy, spd, green_ew))
    print(f"simulated {total} s ({len(vehicles)} vehicles) "
          f"in {time.perf_counter() - t0:.1f} s; {len(frames)} frames captured")
    return frames, sig_xy, geoms


def render(G, frames, sig_xy, geoms, out_path, bbox=None, dot_size=14,
           sig_size=30, title="Each dot is one car", box=None):
    """Draw the recorded frames over the dark network and write a looping GIF.
    bbox = (lon_min, lon_max, lat_min, lat_max) crops to a zoom window.
    box = (lon_min, lon_max, lat_min, lat_max), optional: draws a non-filled
    rectangle at those data coords on every frame (not a crop). Used to bake a
    "zoom window" outline into a full-view render so a companion zoom GIF's
    crop is registered against it by construction, instead of by hand."""
    segs = [np.asarray(g.coords) for g in geoms.values()]

    fig, ax = plt.subplots(figsize=(10, 10), dpi=100)
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.add_collection(LineCollection(segs, colors="#39424e", linewidths=0.7))
    if bbox:
        ax.set_xlim(bbox[0], bbox[1])
        ax.set_ylim(bbox[2], bbox[3])
    else:
        ax.autoscale()
    if box is not None:
        lon0, lon1, lat0, lat1 = box
        ax.add_patch(Rectangle((lon0, lat0), lon1 - lon0, lat1 - lat0,
                                fill=False, edgecolor="#16d6c1", linewidth=2,
                                zorder=5))
    ax.set_aspect(1.0 / math.cos(math.radians(config.STUDY_CENTER[0])))
    ax.axis("off")
    ax.set_title(title, color="#e6edf3", fontsize=15, pad=12)
    fig.text(0.5, 0.045,
             "color = speed (red = stopped, green = free-flowing)   "
             "squares = real traffic signals (east-west approach)",
             color="#9da7b3", fontsize=10, ha="center")

    # dynamic artists, updated in place each frame (fast: no re-draw of the map)
    sig_scatter = ax.scatter(sig_xy[:, 0], sig_xy[:, 1], s=sig_size, marker="s",
                             c="#e74c3c", zorder=3)
    car_scatter = ax.scatter([], [], s=dot_size, c=[], cmap="RdYlGn",
                             vmin=0.0, vmax=DOT_VMAX, zorder=4, linewidths=0)
    clock = ax.text(0.02, 0.02, "", transform=ax.transAxes, color="#9da7b3",
                    fontsize=11, family="monospace")

    images = []
    for i, (xy, spd, green_ew) in enumerate(frames):
        car_scatter.set_offsets(xy)
        car_scatter.set_array(spd)
        sig_scatter.set_color(np.where(green_ew, "#2ecc71", "#e74c3c"))
        clock.set_text(f"t = +{i // 60}:{i % 60:02d}  (10x speed)")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
        buf.seek(0)
        images.append(Image.open(buf).convert("P", palette=Image.ADAPTIVE))
    plt.close(fig)

    images[0].save(out_path, save_all=True, append_images=images[1:],
                   duration=int(1000 / FPS), loop=0, optimize=True)
    print(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.1f} MB, "
          f"{len(images)} frames)")


def busiest_signal(G, frames, sig_xy, sig_nodes):
    """The signal with the most stopped cars nearby (averaged over the recorded
    window): the best place to zoom, because queue-and-release is visible there.
    Returns (lon, lat, label) with a street-name label from the incident edges."""
    lon_r, lat_r = 0.0015, 0.0011          # ~120 m counting radius in degrees
    stopped_near = np.zeros(len(sig_xy))
    for xy, spd, _green in frames:
        stopped = xy[spd < 0.5]
        for i, (sx, sy) in enumerate(sig_xy):
            stopped_near[i] += np.sum(
                (np.abs(stopped[:, 0] - sx) < lon_r)
                & (np.abs(stopped[:, 1] - sy) < lat_r))
    best = int(np.argmax(stopped_near))
    node = sig_nodes[best]
    names = set()
    for u, v, data in list(G.in_edges(node, data=True)) + list(G.out_edges(node, data=True)):
        n = data.get("name")
        if isinstance(n, str):
            names.add(n)
        elif isinstance(n, list):
            names.update(x for x in n if isinstance(x, str))
    label = " & ".join(sorted(names)[:2]) if names else "a signalized intersection"
    return sig_xy[best, 0], sig_xy[best, 1], label


def main():
    G = generate.get_network()
    frames, sig_xy, geoms = record(G)
    sig_nodes = sorted(generate.prepare_signals(G)["nodes"])

    full_path = os.path.join(config.FIGURES_DIR, "cars_moving_full.gif")
    render(G, frames, sig_xy, geoms, full_path,
           title="Each dot is one car  |  SE Powell corridor, 500 vehicles")

    clon, clat, label = busiest_signal(G, frames, sig_xy, sig_nodes)
    bbox = (clon - ZOOM_HALF_LON, clon + ZOOM_HALF_LON,
            clat - ZOOM_HALF_LAT, clat + ZOOM_HALF_LAT)
    zoom_path = os.path.join(config.FIGURES_DIR, "cars_moving_zoom.gif")
    render(G, frames, sig_xy, geoms, zoom_path, bbox=bbox, dot_size=60,
           sig_size=90, title=f"Each dot is one car  |  {label}")


if __name__ == "__main__":
    main()
