"""The four graphic cards for the Aug 14 SSRS Ignite talk: beats 1, 2, 13, 14.

Read-only, no simulation. Beat 14's numbers are recomputed from the saved 12-seed
mixed-fleet closure pairs at build time so the card cannot drift from the runs.
Beats 2 and 13 carry ledger values, quoted with their IDs below.

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

# The one Portland NO2 monitor with published coordinates in our sources
# (DATASETS.md sec. 6 / REFERENCES.md [6]; AQS 41-051-0080, SE Lafayette NCore).
# The second regulatory monitor is a freeway near-road site on I-5 at MP 290.14
# in Tualatin, AQS 41-067-0005. NO latitude/longitude for it appears in any of
# our sources, so it is NOT plotted: an approximate dot on a map reads as a
# surveyed location. It is stated in text instead, which is what we can support.
LAFAYETTE = (45.4966, -122.6029)

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
    ax.text(0.5, 0.14, "Portland State University REU  ·  Teuscher Lab",
            ha="center", va="center", color=MUTED, fontsize=15)
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

    lat, lon = LAFAYETTE
    net.plot([lon], [lat], marker="o", ms=15, color=WARN, zorder=5)
    net.plot([lon], [lat], marker="o", ms=30, mfc="none", mec=WARN, mew=1.6,
             alpha=0.6, zorder=5)
    net.annotate("SE Lafayette\n1 of the 2",
                 xy=(lon, lat), xytext=(lon + 0.055, lat + 0.045),
                 color=INK, fontsize=13, ha="left",
                 arrowprops=dict(arrowstyle="->", color=WARN, lw=1.4), zorder=6)

    ax.text(0.045, 0.72, "2", color=WARN, fontsize=150, fontweight="bold",
            ha="left", va="center")
    ax.text(0.045, 0.50, "regulatory NO$_2$ monitors\nfor 2.5 million people",
            color=INK, fontsize=25, ha="left", va="center", linespacing=1.5)
    # Both monitors fall inside this frame: Tualatin is ~16 km from the study
    # centre and the plotted network reaches 20 km. An earlier draft said the
    # second one was "off to the southwest" and called Lafayette the only monitor
    # in the picture; both were wrong, and checking the bbox is what caught it.
    ax.text(0.045, 0.28,
            "One is marked here. The other is a\n"
            "freeway site on I-5 near Tualatin,\n"
            "in the southwest of this same area.\n\n"
            "So almost everything we know about\n"
            "street-level air is modeled, not measured.",
            color=MUTED, fontsize=15, ha="left", va="center", linespacing=1.6)
    ax.text(0.045, 0.045, "Oregon DEQ 2023 Ambient Monitoring Network Plan",
            color="#5c6672", fontsize=11, ha="left", va="center")
    return _save(fig, "ignite_beat02.png")


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

    net_pct is recomputed from the saved runs, so the claim on the card is the
    claim in the data. M20.17's discipline is explicit that the network total's
    SIGN varies across seeds, so this must never read 'rises slightly'.
    """
    fig, ax = _canvas()
    ax.text(0.5, 0.88, "It did not go away. It moved.",
            ha="center", va="center", color=INK, fontsize=40)

    worst = np.abs(net_pct).max()
    n_up = int((net_pct > 0).sum())
    n_dn = int((net_pct < 0).sum())

    bx = fig.add_axes([0.09, 0.26, 0.36, 0.44], facecolor="none")
    # Both bars the SAME colour on purpose. The message is "these are the same
    # height"; giving the closed bar its own bright colour makes the eye read a
    # difference that is not there, which is the opposite of the point.
    bx.bar([0, 1], [100, 100 + net_pct[0]], color="#3d4d5f", width=0.55)
    bx.set_ylim(0, 125)
    bx.set_xticks([0, 1])
    bx.set_xticklabels(["road open", "road closed"], color=INK, fontsize=15)
    bx.set_yticks([])
    for sp in bx.spines.values():
        sp.set_visible(False)
    bx.tick_params(length=0)
    bx.set_title("NO$_2$ across the whole network",
                 color=MUTED, fontsize=15, pad=12)
    bx.text(0.5, 112, f"{net_pct[0]:+.1f}%", ha="center", color=ACCENT, fontsize=19)

    ax.text(0.56, 0.60,
            f"The network total never moves more\nthan {worst:.1f}% in either direction,\n"
            f"and across 12 runs it goes up {n_up} times\nand down {n_dn}. "
            "It is a coin flip.",
            color=INK, fontsize=19, ha="left", va="center", linespacing=1.7)
    ax.text(0.56, 0.32,
            "But underneath, the map rearranges:\n"
            "Powell drops about 81%, and Division\n"
            "and Holgate rise in 12 runs out of 12.",
            color=MUTED, fontsize=17, ha="left", va="center", linespacing=1.7)
    ax.text(0.5, 0.08,
            "Same cars, same destinations, one blocked street.  "
            "The pollution lands on somebody else.",
            ha="center", va="center", color="#5c6672", fontsize=13)
    return _save(fig, "ignite_beat14.png")


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
        (f"{config.STUDY_RADIUS_M // 1000} km", "across, the\nwhole metro"),
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
    beat01_title(G)
    beat02_monitors(G)
    beat08_scale(G)
    beat13_number()
    beat14_moved(network_totals())
    beat18_failures()


if __name__ == "__main__":
    main()
