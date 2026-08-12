"""The graphic cards for the Aug 14 SSRS Ignite talk.

Read-only, no simulation. Beat 14's numbers are recomputed from the saved 12-seed
mixed-fleet closure pairs at build time so the card cannot drift from the runs.
Beats 2 and 13 carry ledger values, quoted with their IDs below.

Beats 3, 4, 10 and 20 were added Aug 2. They were left title-only on purpose:
choosing them is an editorial call that follows from the script, so they were
built only once the script existed. Notes on those four:

  - 3 and 4 SHARE ONE MAP, drawn by the same function at the same extent, because
    beat 4's whole argument is that the picture did not change. The only thing
    added on 4 is the closure marker. If you edit one, edit both, or the argument
    silently breaks.
  - 3 and 4 deliberately draw the static model's INPUTS (road class, block-group
    population) rather than a fitted land-use surface. Two reasons. The inputs are
    what beat 4's invariance claim (ledger B3) is actually about, and slide 19
    already shows a fitted static surface, so a second one here would spend the
    talk's one blank-panel moment early.
  - 10 is a locator, not a result. No numbers beyond the closure's own geometry,
    which comes from config.CLOSURE and the graph, not from a run.
  - 20 carries no numbers at all, by design (see the script's note on beat 20).
    It reuses beat 1's faint network so the talk closes where it opened.

Built full-bleed at 16:9 to fill the slide, because these four are pure message
cards with no map to frame: at 15 seconds a headline the audience reads in two
seconds beats a title bar plus a small figure. The map slides keep their titles.

Design rules taken from the format, not from taste:
  - One idea per card. If a second idea is worth saying it is worth its own slide,
    and there are no spare slides, so it is not worth saying.
  - The big number is the message. Everything else is small.
  - Caveats go ON SCREEN and UNSPOKEN. A reader can absorb a line of small type in
    the same 15 seconds the speaker spends on the headline, which is the only way
    to be honest about a range inside a five-minute talk.

Usage:  python demos/ignite_cards.py
Writes: outputs/figures/ignite_beat{01,02,13,14}.png
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
from matplotlib.collections import LineCollection

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)
sys.path.append(os.path.join(_ROOT, "src"))

import config
from mixed_rerun import apply_metro_dirs

# Same identity as the animations and the shadow map.
BG = "#0d1117"
INK = "#e6edf3"
MUTED = "#9da7b3"
ACCENT = "#4aa8ff"
WARN = "#ff6a3d"

SEEDS = [42, 7, 13, 21, 99, 2024, 1, 5, 8, 100, 314, 777]

# Both regulatory NO2 monitors, each with surveyed coordinates.
#   SE Lafayette NCore, AQS 41-051-0080: DATASETS.md sec. 6 / REFERENCES.md [6].
#   Tualatin - Bradbury Court (TBC), AQS 41-067-0005, 6745 Bradbury Court:
#     EPA AQS site registry (aqs.epa.gov/aqsweb/airdata/aqs_sites.csv,
#     retrieved Aug 3 2026), 45.3992 / -122.7455, WGS84. Earlier versions
#     plotted only Lafayette because no Tualatin coordinate appeared in our
#     sources and an approximate dot would read as a surveyed location; the
#     registry lookup resolved that, so both are now marked.
LAFAYETTE = (45.4966, -122.6029)
TUALATIN = (45.3992, -122.7455)

# Ledger M20.17 (12-seed mixed-fleet metro closure, near zone <= 1.5 km).
# Powell -80.7% +/- 4.7, range -87.5 to -69.4. The +/- is a standard deviation,
# NOT the envelope; the card shows the envelope so the slide cannot overclaim.
PWL_MEAN, PWL_LO, PWL_HI = 80.7, 69.4, 87.5


def _canvas():
    fig = plt.figure(figsize=(13.333, 7.5), dpi=150, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def _save(fig, name):
    out = os.path.join(config.FIGURES_DIR, name)
    os.makedirs(config.FIGURES_DIR, exist_ok=True)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
    print(f"wrote {out}")
    return out


def beat01_title(G):
    """Beat 1. The question, over the real network so the talk opens on a city."""
    fig, ax = _canvas()
    segs = []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        segs.append(np.asarray(geom.coords) if geom is not None else
                    np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                              [G.nodes[v]["x"], G.nodes[v]["y"]]]))
    net = fig.add_axes([0, 0, 1, 1], facecolor="none")
    net.add_collection(LineCollection(segs, colors="#1c2530", linewidths=0.35))
    net.autoscale()
    lat0 = config.CLOSURE[0]
    net.set_aspect(1.0 / np.cos(np.radians(lat0)))
    net.axis("off")

    ax.set_zorder(2)
    ax.patch.set_alpha(0.0)
    ax.text(0.5, 0.60, "When a road closes,", ha="center", va="center",
            color=INK, fontsize=54, fontweight="light")
    ax.text(0.5, 0.46, "where does the pollution go?", ha="center", va="center",
            color=INK, fontsize=54, fontweight="light")
    ax.text(0.5, 0.20, "Darcy Van Pelt", ha="center", va="center",
            color=MUTED, fontsize=22)
    # Affiliation is the home school, per Christof's Aug 3 ruling ("you should
    # list your school ... even for the paper"); the REU is credited as the
    # program, not the affiliation. Both lines centered: left-aligned text below
    # y~0.10 collides with the deck's "N / 20" counter, centered text clears it.
    ax.text(0.5, 0.14, "Colorado State University Global",
            ha="center", va="center", color=MUTED, fontsize=15)
    ax.text(0.5, 0.09, "NSF REU at Portland State University  ·  Teuscher Lab",
            ha="center", va="center", color=MUTED, fontsize=12)
    return _save(fig, "ignite_beat01.png")


def beat02_monitors(G):
    """Beat 2. Two monitors for the whole metro, so almost everything is modeled."""
    fig, ax = _canvas()
    net = fig.add_axes([0.30, 0.06, 0.66, 0.88], facecolor="none")
    segs = []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        segs.append(np.asarray(geom.coords) if geom is not None else
                    np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                              [G.nodes[v]["x"], G.nodes[v]["y"]]]))
    net.add_collection(LineCollection(segs, colors="#273140", linewidths=0.35))
    net.autoscale()
    net.set_aspect(1.0 / np.cos(np.radians(config.CLOSURE[0])))
    net.axis("off")

    # Both dots identically styled: the message is "this is ALL of them", so
    # neither monitor should look more important than the other.
    for (lat, lon), label, dx, dy in [
            (LAFAYETTE, "SE Lafayette", 0.055, 0.045),
            (TUALATIN, "Tualatin, on I-5", 0.020, 0.052)]:
        net.plot([lon], [lat], marker="o", ms=15, color=WARN, zorder=5)
        net.plot([lon], [lat], marker="o", ms=30, mfc="none", mec=WARN, mew=1.6,
                 alpha=0.6, zorder=5)
        net.annotate(label, xy=(lon, lat), xytext=(lon + dx, lat + dy),
                     color=INK, fontsize=13, ha="left",
                     arrowprops=dict(arrowstyle="->", color=WARN, lw=1.4),
                     zorder=6)

    ax.text(0.045, 0.72, "2", color=WARN, fontsize=150, fontweight="bold",
            ha="left", va="center")
    # "2.5 million": Portland-Vancouver-Hillsboro MSA, 2,512,859 at the 2020
    # Census. Verified Aug 3 2026; the DEQ network serves the metro area.
    ax.text(0.045, 0.50, "regulatory NO$_2$ monitors\nfor 2.5 million people",
            color=INK, fontsize=25, ha="left", va="center", linespacing=1.5)
    # With both monitors marked on the map, the paragraph no longer has to
    # describe where the unplotted one is; it only carries the conclusion.
    ax.text(0.045, 0.30,
            "Both of them are on this map.\n\n"
            "So almost everything we know about\n"
            "street-level air is modeled, not measured.",
            color=MUTED, fontsize=15, ha="left", va="center", linespacing=1.6)
    # y raised clear of the deck's "N / 20" counter (bottom-left, top edge at
    # ~0.067 of slide height), which overlapped the word "Oregon" at y=0.045.
    # Same collision class as beat 3's paragraph; only this card has a
    # left-aligned footer, the others are centered and clear the counter.
    ax.text(0.045, 0.09,
            "Oregon DEQ 2023 Ambient Monitoring Network Plan  ·  "
            "coordinates: EPA AQS site registry",
            color="#5c6672", fontsize=11, ha="left", va="center")
    return _save(fig, "ignite_beat02.png")


# Road classes the static land-use family uses as a predictor, brightest first.
# Drawn dim-to-bright so an arterial reads as an arterial without a legend.
ROAD_CLASSES = [
    ("motorway", "#4aa8ff", 1.5),
    ("trunk", "#3f8fd8", 1.2),
    ("primary", "#3576b0", 1.0),
    ("secondary", "#2d5f8a", 0.7),
    ("tertiary", "#254a68", 0.5),
]
_CLASS_LOOKUP = {n: (c, w) for n, c, w in ROAD_CLASSES}
RESIDENTIAL = ("#1a2330", 0.3)


def _road_class(d):
    """OSM 'highway' can be a string or a list; take the first value we know."""
    hw = d.get("highway")
    for tag in (hw if isinstance(hw, list) else [hw]):
        base = str(tag).replace("_link", "")
        if base in _CLASS_LOOKUP:
            return _CLASS_LOOKUP[base]
    return RESIDENTIAL


def _static_inputs_panel(fig, G, bg, rect):
    """The static model's inputs, drawn once and reused by beats 3 and 4.

    Population as soft block-group blobs, streets colored by road class. These are
    exactly the 'fixed facts' the script names: road type, population, distance to
    a highway (which is a function of the road classes drawn here). Nothing on this
    panel is an output of the simulation, which is the entire point of beat 4.
    """
    ax = fig.add_axes(rect, facecolor="none")

    # Population first so the streets sit on top of it.
    pop = bg["population"].to_numpy(dtype=float)
    scale = 240.0 * pop / max(pop.max(), 1.0)
    ax.scatter(bg["lon"], bg["lat"], s=scale, c="#8a5a2b", alpha=0.30,
               linewidths=0, zorder=1)

    by_style = {}
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        seg = (np.asarray(geom.coords) if geom is not None else
               np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                         [G.nodes[v]["x"], G.nodes[v]["y"]]]))
        by_style.setdefault(_road_class(d), []).append(seg)
    # Dim classes first so arterials draw over residential, not under it.
    for (color, lw), segs in sorted(by_style.items(), key=lambda kv: kv[0][1]):
        ax.add_collection(LineCollection(segs, colors=color, linewidths=lw,
                                         zorder=2))

    ax.autoscale()
    ax.set_aspect(1.0 / np.cos(np.radians(config.CLOSURE[0])))
    ax.axis("off")
    return ax


def beat03_static_way(G, bg):
    """Beat 3. The standard way: fixed facts about a neighborhood.

    The card is deliberately FAIR to the static method. The script's payoff on
    beat 4 only works if the audience has just been told this approach is good,
    so 'it never sees a car move' stays SPOKEN and is not printed here as a jab.
    """
    fig, ax = _canvas()
    _static_inputs_panel(fig, G, bg, [0.34, 0.045, 0.63, 0.90])

    ax.set_zorder(2)
    ax.patch.set_alpha(0.0)
    ax.text(0.045, 0.88, "The standard way", color=INK, fontsize=40,
            ha="left", va="center")
    ax.text(0.045, 0.775, "Predict pollution from fixed facts\nabout a neighborhood.",
            color=INK, fontsize=21, ha="left", va="top", linespacing=1.6)

    for i, (label, sub) in enumerate([
            ("Road type", "highway, arterial, residential"),
            ("Population", "who lives in each block group"),
            ("Distance to a highway", "how close the big roads are")]):
        y = 0.545 - i * 0.135
        ax.text(0.045, y, label, color=ACCENT, fontsize=23, ha="left", va="center")
        ax.text(0.045, y - 0.055, sub, color=MUTED, fontsize=15, ha="left",
                va="center")

    # This paragraph has to thread a narrow gap: the deck's "N / 20" counter sits
    # at the bottom left of every slide, and the input list ends just above. At
    # fontsize 16 it collided with one or the other, so it is set slightly smaller
    # and tighter to sit clear of both.
    ax.text(0.045, 0.118,
            "This is the established method, and it\nworks. Most street-level "
            "pollution maps\nyou have seen were made this way.",
            color=MUTED, fontsize=15, ha="left", va="center", linespacing=1.55)
    # Rao named on the slide (Christof, Aug 12 practice run: cite the prior
    # work at the START for credibility, not only at the comparison). Centered
    # so it clears the bottom-left "N / 20" counter.
    ax.text(0.655, 0.965, "Portland's published static NO$_2$ model: "
            "Rao et al. 2017. My starting point, and my benchmark.",
            ha="center", va="center", color="#5c6672", fontsize=13)
    return _save(fig, "ignite_beat03.png")


def beat04_the_limit(G, bg):
    """Beat 4. The limit: close a road and none of those facts change.

    Ledger B3, the invariance argument. The map panel is byte-identical to beat
    3's by construction (same function, same rect, same data); the ONLY addition
    is the closure marker, so the slide transition shows a picture that refuses
    to move. Do not restyle this panel without restyling beat 3's.
    """
    fig, ax = _canvas()
    panel = _static_inputs_panel(fig, G, bg, [0.34, 0.045, 0.63, 0.90])

    lat0, lon0, _ = config.CLOSURE
    panel.plot([lon0], [lat0], marker="o", ms=16, mfc="none", mec=WARN, mew=2.6,
               zorder=6)
    panel.plot([lon0], [lat0], marker="o", ms=38, mfc="none", mec=WARN, mew=1.4,
               alpha=0.55, zorder=6)
    # Label kept close and pulled up-left: a long leader crossed I-205 and the
    # text ran off the right edge of the slide.
    panel.annotate("road closed here",
                   xy=(lon0, lat0), xytext=(lon0 - 0.011, lat0 + 0.040),
                   color=WARN, fontsize=16, ha="center",
                   arrowprops=dict(arrowstyle="->", color=WARN, lw=1.4), zorder=7)

    ax.set_zorder(2)
    ax.patch.set_alpha(0.0)
    ax.text(0.045, 0.88, "Now close a road.", color=INK, fontsize=40,
            ha="left", va="center")
    ax.text(0.045, 0.775, "Nothing on this map changed.",
            color=WARN, fontsize=26, ha="left", va="center")

    for i, line in enumerate(["Same streets.", "Same people.", "Same jobs."]):
        ax.text(0.045, 0.635 - i * 0.085, line, color=INK, fontsize=23,
                ha="left", va="center")

    ax.text(0.045, 0.29,
            "The inputs did not move, so the\nprediction cannot move either.",
            color=INK, fontsize=20, ha="left", va="center", linespacing=1.7)
    ax.text(0.045, 0.105,
            "It still predicts the same pollution\non a street that now has no cars.",
            color=MUTED, fontsize=16, ha="left", va="center", linespacing=1.7)
    return _save(fig, "ignite_beat04.png")


def beat10_experiment(G):
    """Beat 10. The locator: what 'close 150 m of SE Powell' actually means.

    A locator, not a result. The zone and the segment count come from
    config.CLOSURE and the graph through the SAME helper the simulation uses to
    remove them, so the picture cannot disagree with what was actually closed.
    """
    from generate import closed_edges_in_zone

    fig, ax = _canvas()
    lat0, lon0, radius_m = config.CLOSURE
    closed = set(closed_edges_in_zone(G))
    aspect = 1.0 / np.cos(np.radians(lat0))

    def collect(bbox=None):
        keep, hot = [], []
        for u, v, k, d in G.edges(keys=True, data=True):
            geom = d.get("geometry")
            seg = (np.asarray(geom.coords) if geom is not None else
                   np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                             [G.nodes[v]["x"], G.nodes[v]["y"]]]))
            if bbox is not None:
                x0, x1, y0, y1 = bbox
                if (seg[:, 0].max() < x0 or seg[:, 0].min() > x1 or
                        seg[:, 1].max() < y0 or seg[:, 1].min() > y1):
                    continue
            (hot if (u, v, k) in closed else keep).append(seg)
        return keep, hot

    # Left: the whole metro, with a box around the zone so the zoom has an anchor.
    # Brighter than beat 1's network: at this size the dimmer value read as a grey
    # smudge rather than as a city.
    wide = fig.add_axes([0.045, 0.10, 0.42, 0.62], facecolor="none")
    keep, hot = collect()
    wide.add_collection(LineCollection(keep, colors="#26313f", linewidths=0.35))
    wide.autoscale()
    wide.set_aspect(aspect)
    wide.axis("off")
    half = 0.030
    wide.add_patch(plt.Rectangle((lon0 - half, lat0 - half / aspect),
                                 2 * half, 2 * half / aspect, fill=False,
                                 edgecolor=WARN, lw=1.6, zorder=5))
    wide.set_title("the whole simulated network", color=MUTED, fontsize=15, pad=10)

    # Right: the zone itself. Everything else is context; the closed block is hot.
    z = 0.016
    bbox = (lon0 - z, lon0 + z, lat0 - z / aspect, lat0 + z / aspect)
    near = fig.add_axes([0.53, 0.10, 0.42, 0.62], facecolor="none")
    keep, hot = collect(bbox)
    near.add_collection(LineCollection(keep, colors="#273140", linewidths=0.9))

    # The three arterials the rest of the talk is about, named on screen so that
    # beat 11's "Division and Holgate" lands on streets the room has already seen.
    # Powell is drawn brightest because it is the one that closes.
    for street, color, lw in [
            ("Southeast Powell Boulevard", "#7fb2e0", 2.0),
            ("Southeast Division Street", "#44607e", 1.6),
            ("Southeast Holgate Boulevard", "#44607e", 1.6)]:
        segs, xs, ys = [], [], []
        for u, v, k, d in G.edges(keys=True, data=True):
            nm = d.get("name")
            if street not in (nm if isinstance(nm, list) else [nm]):
                continue
            geom = d.get("geometry")
            seg = (np.asarray(geom.coords) if geom is not None else
                   np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                             [G.nodes[v]["x"], G.nodes[v]["y"]]]))
            if (seg[:, 0].max() < bbox[0] or seg[:, 0].min() > bbox[1] or
                    seg[:, 1].max() < bbox[2] or seg[:, 1].min() > bbox[3]):
                continue
            segs.append(seg)
            xs.extend(seg[:, 0]); ys.extend(seg[:, 1])
        if not segs:
            continue
        near.add_collection(LineCollection(segs, colors=color, linewidths=lw,
                                           zorder=3))
        # Label at the street's left-most point inside the frame, nudged inward.
        i = int(np.argmin(xs))
        near.text(bbox[0] + 0.0012, ys[i] + 0.0006,
                  street.replace("Southeast ", "SE "), color=color, fontsize=13,
                  ha="left", va="bottom", zorder=6)

    near.add_collection(LineCollection(hot, colors=WARN, linewidths=3.4, zorder=4))
    # The zone itself, so the boxy cluster of removed segments reads as "a circle
    # of this radius on Powell" rather than as an arbitrary glyph.
    dlat = radius_m / 111_320.0
    near.add_patch(mpatches.Ellipse((lon0, lat0), 2 * dlat * aspect, 2 * dlat,
                                    fill=False, edgecolor=WARN, lw=1.2,
                                    alpha=0.7, ls="--", zorder=5))
    near.set_xlim(bbox[0], bbox[1])
    near.set_ylim(bbox[2], bbox[3])
    near.set_aspect(aspect)
    near.axis("off")
    near.set_title(f"{int(radius_m)} m of SE Powell Boulevard, removed",
                   color=WARN, fontsize=15, pad=10)

    ax.set_zorder(2)
    ax.patch.set_alpha(0.0)
    ax.text(0.5, 0.90, "The experiment", ha="center", va="center", color=INK,
            fontsize=42)
    ax.text(0.5, 0.815,
            "Close one stretch of road. Run the exact same trips again.",
            ha="center", va="center", color=INK, fontsize=21)
    ax.text(0.5, 0.045,
            f"Same drivers, same destinations, same random seed.  "
            f"{len(closed)} street segments removed.  Nothing else changed.",
            ha="center", va="center", color="#5c6672", fontsize=14)
    return _save(fig, "ignite_beat10.png")


def beat20_who_this_helps(G):
    """Beat 20. Who this helps, plus the acknowledgments.

    NO NUMBERS, by design: the room includes family and researchers from other
    fields, and a figure here would undo the accessibility the whole close is for.
    The acknowledgments sit on the slide to be READ, not spoken.

    The faint network is beat 1's, so the talk closes on the same picture it
    opened on.

    The AI-assistance line is not optional politeness: the REU program requires
    AI assistance to be acknowledged on deliverables, and Christof's Aug 2 email
    named failure to credit AI as a form of academic misconduct.

    CARRIED, NOT VERIFIED: NSF award 2244551 is taken from the chapter's
    acknowledgements. It has never been checked against NSF's own records.
    """
    fig, ax = _canvas()
    segs = []
    for u, v, k, d in G.edges(keys=True, data=True):
        geom = d.get("geometry")
        segs.append(np.asarray(geom.coords) if geom is not None else
                    np.array([[G.nodes[u]["x"], G.nodes[u]["y"]],
                              [G.nodes[v]["x"], G.nodes[v]["y"]]]))
    net = fig.add_axes([0, 0, 1, 1], facecolor="none")
    net.add_collection(LineCollection(segs, colors="#161e29", linewidths=0.3))
    net.autoscale()
    net.set_aspect(1.0 / np.cos(np.radians(config.CLOSURE[0])))
    net.axis("off")

    ax.set_zorder(2)
    ax.patch.set_alpha(0.0)
    ax.text(0.5, 0.88, "Closures are not hypothetical.", ha="center", va="center",
            color=INK, fontsize=42)

    for i, word in enumerate(["Bridge repairs", "Construction", "Emergencies"]):
        ax.text(0.5, 0.745 - i * 0.085, word, ha="center", va="center",
                color=ACCENT, fontsize=26)

    ax.text(0.5, 0.415,
            "They happen constantly, and right now nobody tells\n"
            "the street that inherits the traffic.",
            ha="center", va="center", color=INK, fontsize=24, linespacing=1.7)
    ax.text(0.5, 0.245, "This is a way to find out in advance.",
            ha="center", va="center", color=INK, fontsize=24)

    ax.text(0.5, 0.165, "Thank you.", ha="center", va="center", color=MUTED,
            fontsize=22)
    # Three short lines, not two long ones: at fontsize 11 the single AI sentence
    # ran off both edges of the slide, which is invisible in a PDF render and
    # obvious on a projector.
    ax.text(0.5, 0.075,
            "Christof Teuscher  ·  Niklas Anderson  ·  Dr. Meenakshi Rao (NO$_2$ "
            "measurements)  ·  Teuscher Lab, Portland State University\n"
            "NSF REU award 2244551  ·  Orca cluster, NSF award 2346732\n"
            "AI assistance (Claude, Anthropic) was used for code, figures and "
            "drafting. All results were checked by the author.",
            ha="center", va="center", color="#5c6672", fontsize=11,
            linespacing=1.9)
    return _save(fig, "ignite_beat20.png")


def beat13_number():
    """Beat 13. The headline number, with the honest envelope beneath it.

    The draft script said the result 'lands within about five points every time'.
    That was the standard deviation read as an envelope. Across the 12 runs the
    drop actually spans 69 to 88 percent, so the card states the mean and the
    range and lets the small type carry the spread.
    """
    fig, ax = _canvas()
    ax.text(0.5, 0.80, "Near the closed stretch, modeled NO$_2$ falls",
            ha="center", va="center", color=INK, fontsize=27)
    ax.text(0.5, 0.545, f"{PWL_MEAN:.0f}%", ha="center", va="center",
            color=ACCENT, fontsize=190, fontweight="bold")

    # The spread, drawn rather than asserted: a bar from 69 to 88 with the mean.
    x0, x1, y = 0.26, 0.74, 0.285
    ax.plot([x0, x1], [y, y], color="#2b3948", lw=9, solid_capstyle="round")
    frac = (PWL_MEAN - PWL_LO) / (PWL_HI - PWL_LO)
    ax.plot([x0 + frac * (x1 - x0)], [y], marker="o", ms=17, color=ACCENT, zorder=4)
    ax.text(x0, y - 0.062, f"{PWL_LO:.0f}%", ha="center", color=MUTED, fontsize=15)
    ax.text(x1, y - 0.062, f"{PWL_HI:.0f}%", ha="center", color=MUTED, fontsize=15)
    ax.text(0.5, y + 0.075, "every one of 12 runs landed in here",
            ha="center", color=MUTED, fontsize=16)
    ax.text(0.5, 0.10,
            "12 runs, each with different random traffic.  Mean 80.7%, "
            "no run below 69% or above 88%.",
            ha="center", va="center", color="#5c6672", fontsize=13)
    return _save(fig, "ignite_beat13.png")


def beat14_moved(net_pct):
    """Beat 14. Moved, not removed: the total barely budges, the map rearranges.

    REDESIGNED Aug 12 after the practice run: Christof read the old two-bar
    panel as roads and waited for it to animate, and called this the deck's
    most text-heavy slide (nobody can read a paragraph in 15 seconds). Now a
    beat-13-style big-number card: one claim, one number, two short lines.
    net_pct is still recomputed from the saved runs, so the claim on the card
    is the claim in the data. M20.17's discipline is explicit that the network
    total's SIGN varies across seeds, so this must never read 'rises slightly';
    the card states the bound and the up/down split instead.
    """
    return _beat14_draw(net_pct, phase=4, name="ignite_beat14.png")


def _beat14_draw(net_pct, phase, name):
    """Draw the beat-14 card up to `phase` (1..4). Phase 4 is the full card;
    lower phases power the staged-reveal GIF, whose steps land in sync with
    the four spoken lines so the audience reads one line at a time."""
    fig, ax = _canvas()
    worst = np.abs(net_pct).max()
    n_up = int((net_pct > 0).sum())
    n_dn = int((net_pct < 0).sum())

    ax.text(0.5, 0.88, "It did not go away. It moved.",
            ha="center", va="center", color=INK, fontsize=40)
    if phase >= 2:
        ax.text(0.5, 0.72, "NO$_2$ across the whole network changes by",
                ha="center", va="center", color=MUTED, fontsize=21)
        # ceil keeps the giant number honest: |worst| is 1.7, "under 2%" holds.
        ax.text(0.5, 0.50, f"under {int(np.ceil(worst))}%",
                ha="center", va="center", color=ACCENT, fontsize=120,
                fontweight="bold")
    if phase >= 3:
        ax.text(0.5, 0.29,
                f"in every one of 12 runs  ·  up {n_up}, down {n_dn}, a coin flip",
                ha="center", va="center", color=INK, fontsize=20)
    if phase >= 4:
        ax.text(0.5, 0.175,
                "Underneath, the map rearranges: Powell drops about 81%, and "
                "Division and Holgate rise, 12 runs of 12.",
                ha="center", va="center", color=MUTED, fontsize=16)
        ax.text(0.5, 0.075,
                "Same cars, same destinations, one blocked street.  "
                "The pollution lands on somebody else.",
                ha="center", va="center", color="#5c6672", fontsize=13)
    return _save(fig, name)


def beat14_moved_anim(net_pct):
    """Beat 14 as a staged-reveal GIF for the animated deck (the stills deck
    keeps the static card). Frame timings track the spoken script: headline
    (~2.5 s), the number (~4 s), the coin flip (~3.5 s), then the full card
    held far longer than the slide's 15 s so a GIF loop restart can never
    show on screen."""
    from PIL import Image

    frames, durations = [], [2500, 4000, 3500, 30000]
    for phase in range(1, 5):
        p = _beat14_draw(net_pct, phase, f"_beat14_phase{phase}.png")
        frames.append(Image.open(p).convert("P", palette=Image.ADAPTIVE,
                                            colors=256))
    out = os.path.join(config.FIGURES_DIR, "ignite_beat14_reveal.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0)
    for phase in range(1, 5):
        os.remove(os.path.join(config.FIGURES_DIR, f"_beat14_phase{phase}.png"))
    print(f"wrote {out}")
    return out


def beat08_scale(G):
    """Beat 8. Scale and real data: the trips are measured, not invented.

    Counts are read off the loaded graph rather than quoted, so the card cannot
    drift from the network the runs actually used (ledger R3 / M20 config).
    """
    fig, ax = _canvas()
    ax.text(0.5, 0.88, "And the trips are not invented.",
            ha="center", va="center", color=INK, fontsize=40)

    # Rounded on purpose. Nobody hears "159,410" in a 15-second window, and an
    # exact count invites precision the audience cannot use. The exact values are
    # in the chapter; here the magnitude is the message. Rounding is derived from
    # the live graph so it still cannot drift.
    n_seg = int(round(G.number_of_edges(), -3))
    stats = [
        # STUDY_RADIUS_M is a radius; the label says "across", so print the
        # diameter (fixed Aug 12: the card said 20 km, half the true extent).
        (f"{2 * config.STUDY_RADIUS_M // 1000} km", "across, the\nwhole metro"),
        (f"{n_seg // 1000}k", "street\nsegments"),
        (f"{config.N_VEHICLES:,}", "simulated\nvehicles"),
        ("531k", "real commuter\njourneys"),
    ]
    for i, (big, small) in enumerate(stats):
        x = 0.13 + i * 0.246
        ax.text(x, 0.575, big, ha="center", va="center", color=ACCENT,
                fontsize=42, fontweight="bold", linespacing=1.1)
        ax.text(x, 0.415, small, ha="center", va="center", color=INK,
                fontsize=18, linespacing=1.5)

    ax.text(0.5, 0.255,
            "The journeys come from federal commute records: where people in this\n"
            "area actually live and where they actually work.",
            ha="center", va="center", color=MUTED, fontsize=19, linespacing=1.7)
    ax.text(0.5, 0.075,
            "US Census LEHD LODES home-to-work flows  ·  OpenStreetMap network  ·  "
            "HBEFA emission factors",
            ha="center", va="center", color="#5c6672", fontsize=13)
    return _save(fig, "ignite_beat08.png")


def beat18_failures():
    """Beat 18. The two honest failures, merged onto one slide.

    Ledger M20.10/M20.11/M20.12 for the season result and M20.16 for the fleet.
    The season line must never claim a winter LIFT: the apparent one (M20.6) was
    an artifact of a biased baseline and is retired.
    """
    fig, ax = _canvas()
    ax.text(0.5, 0.89, "Two things that did not work.",
            ha="center", va="center", color=INK, fontsize=40)

    ax.text(0.06, 0.68, "1", color=WARN, fontsize=64, fontweight="bold",
            ha="left", va="center")
    ax.text(0.12, 0.685, "It only helps in summer.",
            color=INK, fontsize=27, ha="left", va="center")
    ax.text(0.12, 0.565,
            "In winter, home heating adds pollution my traffic model knows nothing\n"
            "about, and my method adds nothing at all. I think that is the right answer.",
            color=MUTED, fontsize=17, ha="left", va="center", linespacing=1.7)

    ax.text(0.06, 0.36, "2", color=WARN, fontsize=64, fontweight="bold",
            ha="left", va="center")
    ax.text(0.12, 0.365, "My numbers were four times too high.",
            color=INK, fontsize=27, ha="left", va="center")
    ax.text(0.12, 0.245,
            "I had made every car a diesel. Fixing the fleet cut emissions from 39.1 to\n"
            "9.2 grams per vehicle-hour. The scale changed; the ranking of streets did not.",
            color=MUTED, fontsize=17, ha="left", va="center", linespacing=1.7)

    ax.text(0.5, 0.075,
            "Both found by checking my own work against measurements I had held back.",
            ha="center", va="center", color="#5c6672", fontsize=14)
    return _save(fig, "ignite_beat18.png")


def network_totals():
    """Whole-network NO2 per seed, open vs closed, as a percent change."""
    pcts = []
    for s in SEEDS:
        b = f"sweepmix_powell_{s}"
        o = pd.read_parquet(os.path.join(config.PROCESSED_DIR,
                                         f"{b}_open_segments.parquet"))["nox_g"].sum()
        c = pd.read_parquet(os.path.join(config.PROCESSED_DIR,
                                         f"{b}_closed_segments.parquet"))["nox_g"].sum()
        pcts.append(100.0 * (c - o) / o)      # F_NO2 cancels in a ratio
    p = np.array(pcts)
    print(f"network change: mean {p.mean():+.2f}%  max |{np.abs(p).max():.2f}|%  "
          f"{(p > 0).sum()} up / {(p < 0).sum()} down")
    assert np.abs(p).max() < 2.0, "the 'within 2%' claim no longer holds"
    return p


def main():
    apply_metro_dirs()
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    # The static model's inputs, for beats 3 and 4. Same block-group file the
    # gravity demand and the land-use baseline are built from.
    bg = pd.read_parquet(os.path.join(config.PROCESSED_DIR, "landuse_bg.parquet"))
    beat01_title(G)
    beat02_monitors(G)
    beat03_static_way(G, bg)
    beat04_the_limit(G, bg)
    beat08_scale(G)
    beat10_experiment(G)
    beat13_number()
    beat14_moved(network_totals())
    beat18_failures()
    beat20_who_this_helps(G)


if __name__ == "__main__":
    main()
