"""CLOSURE CAR-DOT ANIMATION for the Progress Update 2 closure slide (demo only).

One looping GIF that answers "show the cars rerouting": the same window around
the SE Powell closure zone, first with the street OPEN, then with it CLOSED,
alternating. Both halves come from real runs of the committed kernel with the
IDENTICAL demand draw (same config, same seed, so the same trips are requested
both ways); the only difference is that the closed half removes the closure
zone's edges from the graph, exactly the way the cited closure experiment does
(generate.apply_closure on a copy). Watching the two states alternate, the dots
visibly leave Powell and stack onto SE Division and SE Holgate.

    outputs/figures/closure_cars_flip.gif   open loop, then closed loop

The to-close stretch is highlighted teal while open and red while closed
(render()'s mark_geoms, drawn from the OPEN graph's geometry both times so the
street stays visible on the map after its edges are removed from the sim).

Governance (per CLAUDE.md, same as animate_cars.py): demo only. Runs its own
two throwaway sims SEQUENTIALLY (never concurrently, one sim at a time);
writes no data files and no checkpoints; only GIFs into FIGURES_DIR
(gitignored). No cited number is produced or touched here.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)                       # repo root: config.py
sys.path.append(os.path.join(_ROOT, "src"))  # src/: generate.py, animate_cars.py, mixed_rerun.py

import config
import generate
import animate_cars
from animate_cars import record, render
from mixed_rerun import apply_metro_dirs

# 60 recorded seconds per state (6 s at 10 fps): the flip totals 120 frames,
# a 12 s loop, matching the size budget reasoning in metro_cars_boxed.py.
animate_cars.RECORD_S = 60

# Zoom window: ~3 km square centered on the closure zone (Powell & SE 26th).
# Same half-extents as metro_cars_boxed.py's downtown window (its comment
# derives the degree math); +/-1.5 km comfortably contains both parallel
# arterials the detours use: SE Division (~700 m north) and SE Holgate
# (~900 m south).
CLAT, CLON, _RADIUS = config.CLOSURE
HALF_LON, HALF_LAT = 0.0192, 0.0135
BBOX = (CLON - HALF_LON, CLON + HALF_LON, CLAT - HALF_LAT, CLAT + HALF_LAT)


def main():
    apply_metro_dirs()          # 20 km metro graph from the metro5k-scaleup worktree
    G = generate.get_network()
    print(f"network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    closed_edges = generate.closed_edges_in_zone(G)
    print(f"closure zone: {len(closed_edges)} edges within {_RADIUS:.0f} m")
    geoms_open = animate_cars.edge_geometries(G)
    closed_geoms = [geoms_open[e] for e in closed_edges]

    # --- state 1: street open (sim runs to completion before the next starts) ---
    frames_o, sig_xy, _ = record(G)
    open_gif = os.path.join(config.FIGURES_DIR, "closure_cars_open.gif")
    render(G, frames_o, sig_xy, geoms_open, open_gif, bbox=BBOX,
           dot_size=45, sig_size=70,
           title="Street OPEN  |  SE Powell at 26th",
           mark_geoms=closed_geoms, mark_color="#16d6c1", tight=True)

    # --- state 2: street closed, same demand draw, zone edges removed ---
    G2 = G.copy()
    generate.apply_closure(G2)
    frames_c, sig_xy2, _ = record(G2)
    closed_gif = os.path.join(config.FIGURES_DIR, "closure_cars_closed.gif")
    # background map drawn from the OPEN geometry so the closed street stays
    # visible (in red) instead of vanishing from the map
    render(G2, frames_c, sig_xy2, geoms_open, closed_gif, bbox=BBOX,
           dot_size=45, sig_size=70,
           title="Street CLOSED  |  same trips, rerouting",
           mark_geoms=closed_geoms, mark_color="#e74c3c", tight=True)

    # --- compose the A/B flip: open loop then closed loop, one GIF ---
    from PIL import Image, ImageSequence
    fo = [f.convert("RGB") for f in ImageSequence.Iterator(Image.open(open_gif))]
    fc = [f.convert("RGB") for f in ImageSequence.Iterator(Image.open(closed_gif))]
    both = fo + fc
    # one shared adaptive palette keeps 120 frames within the slide budget
    pal = both[len(both) // 2].quantize(colors=128, method=Image.MEDIANCUT)
    both = [f.quantize(palette=pal) for f in both]
    out = os.path.join(config.FIGURES_DIR, "closure_cars_flip.gif")
    both[0].save(out, save_all=True, append_images=both[1:], loop=0,
                 duration=100, optimize=True)
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB, {len(both)} frames)")


if __name__ == "__main__":
    main()
