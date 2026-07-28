"""BEFORE/AFTER pair: the single-lane freeway artifact, and the realism fix.

Story for the progress-report slide: the metro model's I-84 Banfield freeway
shows a STANDING QUEUE because every road is modeled single-lane (~1,070
veh/hr cap per the corridor calibration), while real I-84 carries 3-4 lanes
each way. This worktree has gated realism features -- MOBIL explicit lanes +
lane changing (reads real OSM lane counts, clamped to LANES_MAX=3), per-driver
IDM heterogeneity, and Webster signal timing. With MOBIL on, the freeway gets
its real lane count and should discharge far better.

Two sequential sims, same seed, same METRO network window on I-84:
    ARM 1 (before): every realism flag off (the committed single-lane spec).
    ARM 2 (after):  MOBIL_ENABLED + DRIVER_HETEROGENEITY + WEBSTER_ENABLED on.
LANES_ENABLED stays False in both -- it is a different, mutually exclusive
model of the same lanes (generate.build_mobil_context refuses both at once).

Honest attribution expected going in: the freeway relief should come from
lanes/MOBIL (a freeway has no signals for Webster to time, and heterogeneity
mostly adds speed variance, not capacity) -- see the printed verdict at the
end for what this run actually showed.

Governance: demo only, same discipline as demos/realism_showcase.py and
src/animate_cars.py. Runs its own two short sims (no checkpoints, no writes
under data/ anywhere -- including the read-only metro5k-scaleup worktree this
reads its network/demand caches from) and writes only two GIFs into
outputs/demos/ (gitignored). The two sims run SEQUENTIALLY in this one
process and are the only sims running.

Usage:  python demos/jam_before_after.py
Writes: outputs/demos/jam_before.gif
        outputs/demos/jam_after.gif
"""
import os
import sys
import random
import time
import unicodedata

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, "src"))

import numpy as np
import osmnx as ox

import config
import generate as g
import animate_cars

# The 20 km metro graph + LODES/land-use demand caches were built in the
# metro5k-scaleup worktree on main (see src/mixed_rerun.py apply_metro_dirs,
# which this inlines -- that module isn't on this branch). READ-ONLY: this
# script points config's data dirs there but never writes, and never touches
# the checkpoint .pkl files that also live there (we call step_vehicles
# directly in our own loop below, never generate.run_simulation's checkpoint
# path).
METRO_WT = r"C:\dev\portland-traffic-abm\.claude\worktrees\metro5k-scaleup"

WARMUP_S = 600     # sim-seconds before recording, so queues are established
RECORD_S = 60      # sim-seconds recorded, one frame per sim-second
BBOX_HALF_LON = 0.0192   # ~1.5 km half-width (~3 km window) at this latitude
BBOX_HALF_LAT = 0.0135


def apply_metro_dirs():
    data = os.path.join(METRO_WT, "data")
    if not os.path.isdir(os.path.join(data, "network")):
        raise SystemExit(f"metro5k-scaleup worktree data not found at {data}; "
                          "this demo reads the metro20k graph/demand caches from "
                          "there and writes nothing there.")
    config.NETWORK_DIR = os.path.join(data, "network")
    config.RAW_DIR = os.path.join(data, "raw")
    config.PROCESSED_DIR = os.path.join(data, "processed")
    print(f"metro data dirs -> {data} (read-only)")


def _plain(s):
    """Fold to plain lowercase ascii for tag matching (accent/case-insensitive)."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()


def is_i84_edge(data):
    """True if this edge's OSM 'ref' or 'name' names I-84 / the Banfield Freeway.
    Both tags can be a list (OSMnx keeps multiple names/refs on some ways) or a
    single string (the loaded graphml here stores multi-refs semicolon-joined,
    e.g. 'I 84;US 30'), so check both shapes."""
    hay = []
    for key in ("ref", "name"):
        v = data.get(key)
        if isinstance(v, list):
            hay.extend(_plain(x) for x in v)
        elif v is not None:
            hay.append(_plain(v))
    return any(("i 84" in h) or ("i84" in h) or ("banfield" in h) for h in hay)


def crop_geoms(geoms, bbox, pad=0.01):
    """Restrict the drawn street map to what's near the render bbox. Purely a
    speed/size optimization for animate_cars.render (the full metro graph is
    159k edges; without this every one of ~120 frames redraws all of them) --
    it changes nothing about the render() function itself, just what map data
    it is given, so the visible streets inside the bbox are unaffected."""
    lon0, lon1, lat0, lat1 = bbox
    out = {}
    for key, line in geoms.items():
        minx, miny, maxx, maxy = line.bounds
        if maxx < lon0 - pad or minx > lon1 + pad or maxy < lat0 - pad or miny > lat1 + pad:
            continue
        out[key] = line
    return out


def run_arm(label, mobil_on, driver_on, webster_on):
    """Run one arm (fresh graph, fresh vehicles) and record (frames, sig_xy,
    geoms, per-frame edge keys). frames = list of (xy, spd, green_ew), the
    exact format animate_cars.render() expects; edge_keys_per_frame is extra
    (not part of that contract) used only to locate the I-84 jam from arm 1."""
    config.LANES_ENABLED = False           # always off: mutually exclusive w/ MOBIL
    config.MOBIL_ENABLED = mobil_on
    config.DRIVER_HETEROGENEITY = driver_on
    config.WEBSTER_ENABLED = webster_on

    graph_file = os.path.join(config.NETWORK_DIR, "graph.graphml")
    G = ox.load_graphml(graph_file)        # FRESH per arm: prepare_network mutates in place
    if len(G.nodes) < 50000:
        raise SystemExit(f"cached graph at {graph_file} has only {len(G.nodes)} nodes; "
                          "expected the metro20k graph (~62k nodes/~159k edges). Check "
                          "NETWORK_DIR / the metro5k-scaleup worktree.")
    g.prepare_network(G)

    webster_flows = None
    if webster_on:
        # Demo-only economy: half the authoritative warmup (documented in the
        # module docstring / the run's own printout), not the cited default.
        config.WEBSTER_WARMUP_STEPS = 600
        webster_flows = g._measure_approach_flows(
            G, config.N_VEHICLES, config.WEBSTER_WARMUP_STEPS)
    signals = g.prepare_signals(G, flows=webster_flows)

    lanes = {(u, v, k): d.get("n_lanes", 1) for u, v, k, d in G.edges(keys=True, data=True)}
    driver_ctx = g.build_driver_context()
    mobil_ctx = g.build_mobil_context(G)
    if mobil_ctx is not None:
        lanes = None                       # mutually exclusive lane models

    nodes = list(G.nodes)
    rng = random.Random(config.RANDOM_SEED)
    nox_coeffs = g.emissions.active_coeffs()
    demand = g.build_demand_weights(G, nodes)
    through = g.build_through_context(G, nodes)

    vehicles = []
    for vid in range(config.N_VEHICLES):
        veh = g.make_vehicle(G, nodes, rng, vid, demand, through, driver_ctx=driver_ctx)
        if veh is not None:
            vehicles.append(veh)
    print(f"[{label}] {len(vehicles)} vehicles spawned "
          f"(MOBIL={mobil_on} drivers={driver_on} webster={webster_on})")

    geoms = animate_cars.edge_geometries(G)
    sig_nodes = sorted(signals["nodes"])
    sig_xy = np.array([(G.nodes[n]["x"], G.nodes[n]["y"]) for n in sig_nodes])

    seg_tot = {e: 0.0 for e in G.edges(keys=True)}
    seg_nox = {e: 0.0 for e in G.edges(keys=True)}
    seg_thr = {e: 0.0 for e in G.edges(keys=True)}

    frames = []
    edge_keys_per_frame = []
    t0 = time.perf_counter()
    total = WARMUP_S + RECORD_S
    for step in range(total):
        t = step * config.DT
        g.step_vehicles(vehicles, config.DT, t, seg_tot, seg_nox, seg_thr,
                        nox_coeffs, G, nodes, rng, signals, demand, through,
                        driver_ctx=driver_ctx, mobil_ctx=mobil_ctx, lanes=lanes)
        if step >= WARMUP_S:
            xy = np.array([animate_cars.vehicle_xy(v, geoms) for v in vehicles])
            spd = np.array([v["v"] for v in vehicles])
            green_ew = np.array([g.is_green(signals, n, 0, t) for n in sig_nodes])
            frames.append((xy, spd, green_ew))
            edge_keys_per_frame.append([v["route"][v["idx"]][:3] for v in vehicles])
        if (step + 1) % 200 == 0:
            print(f"  [{label}] step {step + 1}/{total} "
                  f"({time.perf_counter() - t0:.0f}s elapsed)")
    print(f"[{label}] simulated {total}s, recorded {len(frames)} frames "
          f"in {time.perf_counter() - t0:.1f}s")
    return G, frames, sig_xy, geoms, edge_keys_per_frame


def locate_i84_jam(G, frames, edge_keys_per_frame):
    """Center of mass of STOPPED cars on I-84/Banfield edges, pooled over every
    recorded frame -- pooling over time means a spot that stays jammed for many
    seconds naturally dominates the average, which is exactly 'where stopped
    cars are densest'. Returns (center_lon, center_lat, anchor_label)."""
    i84_edges = {(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
                 if is_i84_edge(d)}
    if not i84_edges:
        raise SystemExit("no I-84/Banfield edges found in this graph by ref/name match")
    pts = []
    for (xy, spd, _green), edge_keys in zip(frames, edge_keys_per_frame):
        on_i84 = np.array([ek in i84_edges for ek in edge_keys])
        mask = on_i84 & (spd < 0.5)
        if mask.any():
            pts.append(xy[mask])
    if not pts:
        raise SystemExit("no stopped cars found on I-84/Banfield in the recorded "
                         "BEFORE window; cannot locate the jam window")
    stacked = np.vstack(pts)
    cx, cy = float(stacked[:, 0].mean()), float(stacked[:, 1].mean())

    # label the anchor with the nearest I-84 edge's street name
    best_d2, best_name = None, None
    for u, v, k in i84_edges:
        d = G.get_edge_data(u, v, k)
        mx = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2.0
        my = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2.0
        d2 = (mx - cx) ** 2 + (my - cy) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            name = d.get("name")
            best_name = name if isinstance(name, str) else (
                "/".join(name) if isinstance(name, list) else str(name))
    print(f"I-84 jam located at ({cx:.5f}, {cy:.5f}) from {len(stacked)} pooled "
          f"stopped-car observations across {len(pts)} frames; nearest edge "
          f"name '{best_name}'")
    return cx, cy, best_name


def measure_window(frames, bbox):
    """Averaged over the recorded window: mean stopped-car count and mean speed
    of every car inside bbox. DEMO numbers -- one seed, one 60s window."""
    lon0, lon1, lat0, lat1 = bbox
    stopped_counts, mean_speeds = [], []
    for xy, spd, _green in frames:
        inside = ((xy[:, 0] >= lon0) & (xy[:, 0] <= lon1)
                  & (xy[:, 1] >= lat0) & (xy[:, 1] <= lat1))
        if not inside.any():
            stopped_counts.append(0)
            continue
        stopped_counts.append(int((spd[inside] < 0.5).sum()))
        mean_speeds.append(float(spd[inside].mean()))
    return (float(np.mean(stopped_counts)),
            float(np.mean(mean_speeds)) if mean_speeds else float("nan"))


def main():
    apply_metro_dirs()
    assert config.RANDOM_SEED == 42, "pin the seed before citing these numbers"
    assert config.STUDY_RADIUS_M == 20000, "expected the committed metro20k radius"
    assert config.N_VEHICLES == 16500, "expected the committed metro20k vehicle count"
    assert config.DEMAND_LODES_OD is True, "expected the committed metro20k LODES OD demand"
    print(f"config verified: metro20k settings (seed {config.RANDOM_SEED}, "
          f"{config.STUDY_RADIUS_M / 1000:.0f} km, {config.N_VEHICLES} vehicles, "
          f"LODES OD {config.DEMAND_LODES_OD})")

    out_dir = os.path.join(WT, "outputs", "demos")
    os.makedirs(out_dir, exist_ok=True)

    print(f"\n{'=' * 66}\nARM 1: BEFORE -- all realism flags off\n{'=' * 66}")
    G1, frames1, sig_xy1, geoms1, edges1 = run_arm("before", False, False, False)

    cx, cy, anchor = locate_i84_jam(G1, frames1, edges1)
    bbox = (cx - BBOX_HALF_LON, cx + BBOX_HALF_LON, cy - BBOX_HALF_LAT, cy + BBOX_HALF_LAT)
    print(f"shared bbox for both renders: lon [{bbox[0]:.5f}, {bbox[1]:.5f}], "
          f"lat [{bbox[2]:.5f}, {bbox[3]:.5f}]")

    print(f"\n{'=' * 66}\nARM 2: AFTER -- MOBIL + driver heterogeneity + Webster\n{'=' * 66}")
    G2, frames2, sig_xy2, geoms2, edges2 = run_arm("after", True, True, True)

    before_stop, before_speed = measure_window(frames1, bbox)
    after_stop, after_speed = measure_window(frames2, bbox)
    print(f"\n{'=' * 66}\nDEMO NUMBERS (one seed 42, {RECORD_S}s recorded window, "
          f"bbox anchored on '{anchor}') -- demo evidence, not a calibration claim\n{'=' * 66}")
    print(f"  BEFORE: mean stopped cars in-window {before_stop:.1f}, "
          f"mean speed {before_speed:.2f} m/s")
    print(f"  AFTER : mean stopped cars in-window {after_stop:.1f}, "
          f"mean speed {after_speed:.2f} m/s")

    before_path = os.path.join(out_dir, "jam_before.gif")
    after_path = os.path.join(out_dir, "jam_after.gif")
    animate_cars.render(G1, frames1, sig_xy1, crop_geoms(geoms1, bbox), before_path,
                        bbox=bbox, dot_size=45,
                        title="Single lane: the jam stands still")
    animate_cars.render(G2, frames2, sig_xy2, crop_geoms(geoms2, bbox), after_path,
                        bbox=bbox, dot_size=45,
                        title="Real lanes + realism features on")
    print(f"\nwrote {before_path} and {after_path}")


if __name__ == "__main__":
    main()
