"""REGISTERED metro car-dot GIF pair for the progress-report slide (demo only).

The committed deck currently pairs cars_moving_metro.gif (full 20 km metro) with
cars_moving_metro_busy2.gif (a hand-cropped downtown zoom) with NO shared
registration between them: the "area shown at right" box drawn by hand on the
slide does not match the zoom's real crop. This script fixes that by
construction: it records ONE simulation, picks ONE bbox, and renders both GIFs
from that same bbox, so the teal box baked into the full view and the zoom's
crop are the exact same rectangle.

    outputs/figures/cars_moving_metro_boxed.gif       full metro + teal box
    outputs/figures/cars_moving_metro_zoom_boxed.gif  zoom, cropped to that box

Reuses src/animate_cars.py's own record()/render()/busiest_signal() so the
look (dark background, red=stopped/green=flowing dots, signal squares, clock,
legend line) matches the existing deck GIFs exactly; the only new thing is the
optional `box=` rectangle argument added to render().

Governance (per CLAUDE.md and the task brief): demo only, same as
animate_cars.py itself. Runs its own small sim (positions are never saved in
data/); writes nothing but these two GIFs to FIGURES_DIR (gitignored); no
checkpoints; no other simulation is running at the same time as this one.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)                       # repo root: config.py
sys.path.append(os.path.join(_ROOT, "src"))  # src/: generate.py, animate_cars.py, mixed_rerun.py

import config
import generate
import animate_cars                       # module, so we can override RECORD_S
from animate_cars import record, render
from mixed_rerun import apply_metro_dirs

# Fewer recorded seconds than animate_cars' default 120: at metro scale 120
# frames of 16,500 dots rendered a 10 MB GIF; 60 frames (still a 6 s / 10 fps
# loop) keeps it under the slide's ~5 MB budget with no visible loss.
animate_cars.RECORD_S = 60

# Downtown Portland core (SW 5th & Washington sits one block off this). Centering
# the zoom HERE, not on busiest_signal(), is deliberate: busiest_signal() maximizes
# stopped cars, which at metro scale lands on a saturated SINGLE-LANE arterial in
# the suburbs -- i.e. the standing-queue capacity artifact we do NOT want to
# feature. Downtown's dense signalized grid is the honest, visually rich subject
# (it is what the old hand-cropped busy2.gif showed), so we anchor there instead.
DOWNTOWN_LON, DOWNTOWN_LAT = -122.6765, 45.5202

# Zoom window: ~3.0 km square, large enough to read as a clear box on the full
# 20 km frame while still showing individual cars/signals in the crop (the
# task's "roughly 2.5-3.5 km" target; the corridor default ZOOM_HALF_* in
# animate_cars.py is ~1 km total width, an invisible dot at this scale).
# Degrees-per-metre at STUDY_CENTER (45.49854 N): 1 deg lat = 111,320 m;
# 1 deg lon = 111,320 * cos(45.49854 deg) = 78,020 m (longitude is
# foreshortened this far north, which is also why render() applies the
# 1/cos(lat) aspect correction). Half-extent 1,500 m each direction:
#   lat: 1500 / 111320 = 0.01347 deg  (rounded to 0.0135)
#   lon: 1500 /  78020 = 0.01922 deg  (rounded to 0.0192)
# giving a box ~3.01 km (N-S) x ~3.04 km (E-W): a square, not a rounding
# accident, to the precision this matters at.
ZOOM_HALF_LON = 0.0192
ZOOM_HALF_LAT = 0.0135


def main():
    apply_metro_dirs()          # point NETWORK_DIR/RAW_DIR/PROCESSED_DIR at the
                                 # metro5k-scaleup worktree's 20 km graph.graphml
    G = generate.get_network()
    print(f"network: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    frames, sig_xy, geoms = record(G)

    # Center the zoom on the signalized node nearest downtown (see DOWNTOWN_*
    # above for why here and not busiest_signal). Label it from that node's
    # street names, the same way busiest_signal does.
    sig_nodes = sorted(generate.prepare_signals(G)["nodes"])
    cnode = min(sig_nodes, key=lambda n: (G.nodes[n]["x"] - DOWNTOWN_LON) ** 2
                                        + (G.nodes[n]["y"] - DOWNTOWN_LAT) ** 2)
    clon, clat = G.nodes[cnode]["x"], G.nodes[cnode]["y"]
    names = set()
    for u, v, d in list(G.in_edges(cnode, data=True)) + list(G.out_edges(cnode, data=True)):
        nm = d.get("name")
        if isinstance(nm, str):
            names.add(nm)
        elif isinstance(nm, list):
            names.update(x for x in nm if isinstance(x, str))
    label = "Downtown Portland"
    bbox = (clon - ZOOM_HALF_LON, clon + ZOOM_HALF_LON,
            clat - ZOOM_HALF_LAT, clat + ZOOM_HALF_LAT)
    print(f"zoom window centered on downtown ({' & '.join(sorted(names)[:2])}): bbox={bbox}")

    # Jul 28 legibility fix (Darcy's catch, morning of the talk): the old sizes
    # (zoom sig_size 70 vs dot 45, streets at the faint default) let downtown's
    # 375 signal squares cover the street grid entirely, so the squares read as
    # "traffic lights with no roads". Flip the visual hierarchy: signals SMALLER
    # than cars, streets bright enough to see under them. New filenames so the
    # old pair survives until the new one is eyeballed.
    full_path = os.path.join(config.FIGURES_DIR, "cars_moving_metro_boxed2.gif")
    render(G, frames, sig_xy, geoms, full_path, box=bbox, sig_size=12,
           street_lw=0.8,
           title="Each dot is one car  |  Portland metro, 16,500 vehicles")

    zoom_path = os.path.join(config.FIGURES_DIR, "cars_moving_metro_zoom_boxed2.gif")
    render(G, frames, sig_xy, geoms, zoom_path, bbox=bbox, dot_size=45,
           sig_size=24, street_color="#586474", street_lw=1.6,
           title=f"Each dot is one car  |  {label}")

    # Keep the full metro GIF under the slide's ~5 MB budget: if PillowWriter's
    # per-frame palette left it larger, re-encode once with a single shared
    # adaptive palette (visually identical at this dot size, roughly half the
    # bytes). The zoom is already small (sparse crop), so it is left as is.
    for p in (full_path,):
        mb = os.path.getsize(p) / 1e6
        if mb > 5.0:
            from PIL import Image, ImageSequence
            im = Image.open(p)
            fr = [f.convert("RGB") for f in ImageSequence.Iterator(im)]
            pal = fr[len(fr) // 2].quantize(colors=128, method=Image.MEDIANCUT)
            fr = [f.quantize(palette=pal) for f in fr]
            fr[0].save(p, save_all=True, append_images=fr[1:], loop=0,
                       duration=im.info.get("duration", 100), optimize=True)
            print(f"  re-encoded {os.path.basename(p)}: {mb:.1f} -> "
                  f"{os.path.getsize(p) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
