"""UPSTREAM-SHADOW ANIMATION for the Aug 14 SSRS Ignite talk, beat 15.

The animated companion to upstream_shadow_map.py. Same data, same reproduction
gate, same palette; the only difference is that a measuring ring sweeps outward
from the closure zone and each street lights up as the ring reaches it.

Why animate a map that already works as a still: the beat is not "here is where
NO2 moved", it is "the effect reaches FURTHER than the old model could see". A
still map states that. A sweep makes the audience watch streets keep appearing
after the ring has left the blocked stretch behind, which is the same claim
delivered by the eye instead of by the caption. In a 15-second auto-advancing
window that matters, because the picture has to carry meaning without narration.

Two things this adds to the still map:
  1. The dashed 1.5 km circle, the old corridor model's study radius. Everything
     that lights up outside it is change that model was structurally incapable of
     representing. That is the argument for having gone to metro scale, made
     visually. Measured: 61 of the 165 robustly-changed segments (37%) sit
     outside it, carrying a net -356 g.
  2. Label timing. Each street's name and gram total appear only once its street
     is revealed, so the numbers read as findings the sweep turned up rather than
     as a caption that was always there.

Read-only, no simulation. Imports its data path from upstream_shadow_map so the
two assets can never disagree: same 12 mixed-fleet sweep pairs, same ledger
M20.18 gate, which aborts before writing if the numbers stop reproducing.

Timing is pinned to the Ignite format (settled Aug 1 2026: the official SSRS
registration form specifies 15 s per slide). One sweep then a long hold, filling
the window exactly once, because a short looping GIF restarts mid-sentence.

Usage:  python demos/upstream_shadow_anim.py
Writes: outputs/figures/upstream_shadow_anim.gif
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.collections import LineCollection
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import Circle

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)
sys.path.append(os.path.join(_ROOT, "src"))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
import generate
from closure_robustness import name_of
from mixed_rerun import apply_metro_dirs
# Reuse the committed loader, gate, anchors and palette verbatim. The static map
# stays the single source of truth for what this figure asserts.
from upstream_shadow_map import (BG, INK, MUTED, STREET, ZONE_M, check_gate,
                                 load_deltas, street_anchor)

SLIDE_SECONDS = 15.0    # the Ignite window this has to fill exactly
FPS = 9
N_SWEEP = 46            # ~5.1 s outward sweep, the rest holds on the finished map
CORRIDOR_M = 1500.0     # the old corridor model's study radius
HALF_M = 3400.0         # window, matching upstream_shadow_map.render


def build(G, mean_seg, center, out_path):
    lat0, lon0 = center
    dlat = HALF_M / 111320.0
    dlon = HALF_M / (111320.0 * np.cos(np.radians(lat0)))
    bbox = (lon0 - dlon, lon0 + dlon, lat0 - dlat, lat0 + dlat)

    # Same split as the still map: faint base streets, coloured movers. Distance
    # to the zone is carried alongside so the sweep knows when to reveal each one.
    segs_gray, segs_col, vals, dists = [], [], [], []
    for (u, v, k), row in mean_seg.iterrows():
        d = G.get_edge_data(u, v, k)
        if d is None:
            continue
        xu, yu = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        xv, yv = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        mx, my = 0.5 * (xu + xv), 0.5 * (yu + yv)
        if not (bbox[0] <= mx <= bbox[1] and bbox[2] <= my <= bbox[3]):
            continue
        geom = d.get("geometry")
        coords = np.asarray(geom.coords) if geom is not None else np.array(
            [(xu, yu), (xv, yv)])
        if abs(row["delta"]) < 0.5:
            segs_gray.append(coords)
        else:
            segs_col.append(coords)
            vals.append(row["delta"])
            dists.append(generate._haversine_m(lat0, lon0, my, mx))

    for u, v, k in G.edges(keys=True):
        if (u, v, k) in mean_seg.index:
            continue
        xu, yu = float(G.nodes[u]["x"]), float(G.nodes[u]["y"])
        xv, yv = float(G.nodes[v]["x"]), float(G.nodes[v]["y"])
        if bbox[0] <= 0.5 * (xu + xv) <= bbox[1] and bbox[2] <= 0.5 * (yu + yv) <= bbox[3]:
            d = G.get_edge_data(u, v, k)
            geom = d.get("geometry")
            segs_gray.append(np.asarray(geom.coords) if geom is not None
                             else np.array([(xu, yu), (xv, yv)]))

    vals = np.array(vals)
    dists = np.array(dists)

    cmap = LinearSegmentedColormap.from_list(
        "shadow", ["#4aa8ff", "#1d3a5c", BG, "#5c2a1d", "#ff6a3d"])
    vmax = float(np.percentile(np.abs(vals), 88))
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=0.0, vmax=vmax)
    base_rgba = cmap(norm(vals))

    # Square figure, full-bleed axes (Aug 3): the map window is exactly square
    # (the meters-to-degrees conversion cancels the aspect correction), so the
    # old 10 x 7.5 frame letterboxed it with dead side margins. On the slide the
    # art sits under its own title, so the internal title and outside caption
    # moved inside the axes and the axes now fill the whole frame.
    fig, ax = plt.subplots(figsize=(7.5, 7.5), dpi=140)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    ax.add_collection(LineCollection(segs_gray, colors=STREET, linewidths=0.6))
    lc = LineCollection(segs_col, colors=base_rgba, linewidths=2.0, zorder=3)
    ax.add_collection(lc)
    ax.set_xlim(bbox[0], bbox[1])
    ax.set_ylim(bbox[2], bbox[3])
    ax.set_aspect(1.0 / np.cos(np.radians(lat0)))
    ax.axis("off")

    _, _, zone_r = config.CLOSURE
    ax.add_patch(Circle((lon0, lat0), (zone_r / 111320.0) * 3.0, fill=False,
                        edgecolor="#e8112d", linewidth=2.0, zorder=6))

    # The old corridor model's edge.
    theta = np.linspace(0, 2 * np.pi, 240)
    dlat_c = CORRIDOR_M / 111320.0
    dlon_c = CORRIDOR_M / (111320.0 * np.cos(np.radians(lat0)))
    ax.plot(lon0 + dlon_c * np.cos(theta), lat0 + dlat_c * np.sin(theta),
            color=MUTED, lw=1.2, ls="--", alpha=0.65, zorder=4)
    ax.annotate("edge of the old 1.5 km model", xy=(lon0, lat0 + dlat_c),
                xytext=(lon0, lat0 + dlat_c * 1.09), color=MUTED, fontsize=9.5,
                ha="center", va="center", zorder=7)

    # Labels: identical text to the still map, revealed with their street.
    timed = []
    for street, label, dxy in [
        ("Southeast McLoughlin Boulevard",
         "SE McLoughlin  −12% (−114 g)\nquieter on 12 of 12 runs", (-0.010, 0.004)),
        ("Southeast Foster Road",
         # offset pulled left (Aug 3): in the full-bleed square frame the old
         # (+0.008) offset pushed the label off the right edge
         "SE Foster  −90% (−81 g)\nquieter on 12 of 12 runs", (-0.013, -0.007)),
    ]:
        x, y = street_anchor(G, mean_seg, street, center, ZONE_M)
        art = ax.annotate(label, xy=(x, y), xytext=(x + dxy[0], y + dxy[1]),
                          color=INK, fontsize=11, ha="center", zorder=7,
                          arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))
        reveal = generate._haversine_m(lat0, lon0, y, x)
        timed.append((art, reveal))

    for street, label, dxy in [
        ("Southeast Division Street", "SE Division (rises)", (0.012, 0.0022)),
        ("Southeast Holgate Boulevard", "SE Holgate (rises)", (0.004, -0.0040)),
    ]:
        x, y = street_anchor(G, mean_seg, street, center, ZONE_M)
        art = ax.annotate(label, xy=(x + dxy[0], y + dxy[1]), color=MUTED,
                          fontsize=9.5, ha="center", zorder=7)
        timed.append((art, generate._haversine_m(lat0, lon0, y, x)))

    zone_lbl = ax.annotate("SE Powell closed here\n(near zone −81% ± 5, 12-run mean)",
                           xy=(lon0 + 0.011, lat0 - 0.0045), ha="center", va="top",
                           color=INK, fontsize=11, zorder=7)
    timed.append((zone_lbl, 0.0))

    # No internal title: slide 15's own title carries the message, and the old
    # one duplicated it while costing map area. Caption text unchanged, drawn
    # inside the axes' bottom edge instead of in figure margin space.
    ax.text(0.5, 0.012, "mean change in modeled NO₂ across 12 runs  "
            "(blue = less, orange = more, dark = unchanged)   "
            "mixed fleet, metro network",
            transform=ax.transAxes, color=MUTED, fontsize=8.2,
            ha="center", va="bottom", zorder=8)

    ring, = ax.plot([], [], color="#ffd447", lw=1.5, alpha=0.75, zorder=5)
    # Sweep readout moved to the top-left corner (gray-street territory) so the
    # caption owns the bottom edge without collision.
    readout = ax.text(0.015, 0.965, "", transform=ax.transAxes, color="#ffd447",
                      fontsize=13, family="monospace", zorder=8)

    n_hold = int(round(SLIDE_SECONDS * FPS)) - N_SWEEP
    radii = np.concatenate([np.linspace(0.0, HALF_M, N_SWEEP),
                            np.full(n_hold, HALF_M)])

    def update(i):
        r = radii[i]
        rgba = base_rgba.copy()
        rgba[:, 3] = np.where(dists <= r, 1.0, 0.0)
        lc.set_colors(rgba)
        rd = r / 111320.0
        rl = r / (111320.0 * np.cos(np.radians(lat0)))
        ring.set_data(lon0 + rl * np.cos(theta), lat0 + rd * np.sin(theta))
        readout.set_text(f"{r/1000:4.1f} km from the closure")
        for art, reveal in timed:
            a = 1.0 if r >= reveal else 0.0
            art.set_alpha(a)
            # Annotation.set_alpha only touches the text. The leader arrow is a
            # separate patch, so without this it hangs in the dark pointing at a
            # street that has not appeared yet.
            if art.arrow_patch is not None:
                art.arrow_patch.set_alpha(a)
        return lc, ring, readout

    anim = FuncAnimation(fig, update, frames=len(radii), interval=1000 // FPS, blit=False)
    anim.save(out_path, writer=PillowWriter(fps=FPS))
    plt.close(fig)
    print(f"\nwrote {out_path} ({os.path.getsize(out_path)/1e6:.1f} MB, "
          f"{len(radii)/FPS:.1f} s = {N_SWEEP/FPS:.1f} s sweep + {n_hold/FPS:.1f} s hold)")


def main():
    apply_metro_dirs()
    G, mean_seg, per_seed_street, center = load_deltas()
    check_gate(per_seed_street)          # same abort-on-drift gate as the still map
    out = os.path.join(config.FIGURES_DIR, "upstream_shadow_anim.gif")
    build(G, mean_seg, center, out)


if __name__ == "__main__":
    main()
