"""Pedagogical animation: signal-queue discharge, 1 lane vs 2 virtual lanes.

Renders the same tiny hand-checkable scenario as src/lanes_scenarios.py (40
cars queued at a red light, 30 s red then 30 s green) through the REAL kernel
(generate.step_vehicles), once with 1 lane and once with 2 virtual lanes, as
a stacked two-panel GIF so the discharge doubling is visible: the queue
re-packs two-abreast during the red, discharges in pairs on green, and the
counters land on the exact numbers the test file asserts (11 vs 22).

Built Jul 14 2026 while walking Darcy through the experiment. Touches no
project data: reads nothing from data/, writes only into outputs/demos/
(gitignored). Run: python demos/lane_discharge_anim.py
"""
import os
import sys
import random
from collections import defaultdict

WT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, "src"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter

import config
import emissions
from generate import step_vehicles

KPH = 1.0 / 3.6
OUT = os.path.join(WT, "outputs", "demos")

# colors: two lanes = two fixed categorical hues (blue, orange, CVD-safe);
# signal state is never color-alone (the RED/GREEN text label carries it too)
LANE_C = ["#2563eb", "#d97706"]
RED_C, GREEN_C = "#dc2626", "#16a34a"
INK, MUTED = "#374151", "#6b7280"


def signal_at_2():
    """Same deterministic signal as lanes_scenarios: green [0,30), red [30,60)."""
    return {"nodes": {2}, "offset": {2: 0.0},
            "edge_phase": {(1, 2, 0): 0, (2, 3, 0): 0},
            "cycle": 60.0, "green_split": 0.5}


def queued_vehicles(n=40):
    """n cars single-file at the stop line of a 400 m edge (IDM equilibrium)."""
    v0 = 50 * KPH
    route = [(1, 2, 0, 400.0, v0), (2, 3, 0, 600.0, v0)]
    return [{"id": j, "route": list(route), "idx": 0,
             "pos": 398.0 - 7.0 * j, "v": 0.0} for j in range(n)]


def run(n_lanes):
    """Simulate 30 s red + 30 s green; snapshot every step.

    Lane identity for DISPLAY is id % n_lanes (stable across frames); in the
    kernel it is queue rank mod N, the same interleaving, just recomputed.
    """
    lanes = {(1, 2, 0): n_lanes, (2, 3, 0): n_lanes}
    vehs = queued_vehicles(40)
    signals = signal_at_2()
    coeffs = emissions.active_coeffs()
    thru = defaultdict(float)
    seg_tot, seg_nox = defaultdict(float), defaultdict(float)
    steps_per_s = int(round(1.0 / config.DT))
    t0 = 30 * steps_per_s                      # sim starts at t=30 s: red just began
    frames = []

    def snap(t_now):
        pts = []
        for v in vehs:
            key = v["route"][v["idx"]][:3]
            x = v["pos"] + (400.0 if key == (2, 3, 0) else 0.0)
            pts.append((x, v["id"] % n_lanes))
        frames.append({"pts": pts, "crossed": int(thru[(1, 2, 0)]), "t": t_now})

    snap(30.0)
    for s in range(60 * steps_per_s):          # 30 s red + 30 s green
        t = (t0 + s) * config.DT
        step_vehicles(vehs, config.DT, t, seg_tot, seg_nox, thru, coeffs,
                      None, [], random.Random(0), signals, None, None,
                      lanes=lanes)
        snap(t + config.DT)
    return frames


def main():
    os.makedirs(OUT, exist_ok=True)
    runs = {1: run(1), 2: run(2)}
    print(f"crossed on green: 1 lane = {runs[1][-1]['crossed']}, "
          f"2 lanes = {runs[2][-1]['crossed']}")

    n_frames = len(runs[1])
    stride = max(1, n_frames // 61)            # ~61 displayed frames regardless of DT
    idxs = list(range(0, n_frames, stride))
    if idxs[-1] != n_frames - 1:
        idxs.append(n_frames - 1)

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 4.6), sharex=True, dpi=110)
    fig.subplots_adjust(hspace=0.35, left=0.02, right=0.98, top=0.86, bottom=0.12)
    titles = {1: "1 lane (the base model)", 2: "2 virtual lanes"}
    scats, counters, lights = {}, {}, {}

    for ax, nl in zip(axes, (1, 2)):
        ax.set_xlim(90, 540)
        ax.set_ylim(-1.4, 1.4)
        ax.set_yticks([])
        for sp in ("left", "right", "top"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#d1d5db")
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.axhspan(-0.9, 0.9, color="#e5e7eb", zorder=0)          # the road
        lights[nl] = ax.axvline(400, color=RED_C, lw=3, zorder=3)  # the signal
        ax.set_title(titles[nl], loc="left", fontsize=10, color=INK)
        counters[nl] = ax.text(0.99, 1.02, "", transform=ax.transAxes,
                               ha="right", va="bottom", fontsize=10, color=INK)
        scats[nl] = ax.scatter([], [], s=42, edgecolors="white",
                               linewidths=0.5, zorder=4)
        if nl == 2:                            # direct lane labels, not a legend
            ax.text(94, 0.45, "lane 1", fontsize=8, color=LANE_C[0], va="center")
            ax.text(94, -0.45, "lane 2", fontsize=8, color=LANE_C[1], va="center")

    axes[1].set_xlabel("distance along the street (m), stop line at 400 m",
                       fontsize=9, color=MUTED)
    phase_txt = fig.text(0.02, 0.94, "", fontsize=11, color=INK)
    fig.text(0.98, 0.94, "same 40 cars, same physics, same signal",
             ha="right", fontsize=9, color=MUTED)

    def y_of(lane, nl):
        return 0.0 if nl == 1 else (0.45 if lane == 0 else -0.45)

    def update(k):
        i = idxs[k]
        t = runs[1][i]["t"]
        phase = t % 60.0                      # cycle-local time: green [0,30), red [30,60)
        green = phase / 60.0 < 0.5
        if green:
            phase_txt.set_text(f"GREEN  ({phase:.0f} s of the 30 s green used)")
            phase_txt.set_color(GREEN_C)
        else:
            phase_txt.set_text(f"RED  ({60 - phase:.0f} s until green)")
            phase_txt.set_color(RED_C)
        for nl in (1, 2):
            fr = runs[nl][i]
            xs = [p[0] for p in fr["pts"]]
            ys = [y_of(p[1], nl) for p in fr["pts"]]
            cs = [LANE_C[p[1]] for p in fr["pts"]]
            scats[nl].set_offsets(list(zip(xs, ys)))
            scats[nl].set_facecolors(cs)
            counters[nl].set_text(f"through the gate: {fr['crossed']}")
            lights[nl].set_color(GREEN_C if green else RED_C)
        return []

    anim = FuncAnimation(fig, update, frames=len(idxs), blit=False)
    gif = os.path.join(OUT, "lane_discharge.gif")
    anim.save(gif, writer=PillowWriter(fps=6))
    print("wrote", gif)


if __name__ == "__main__":
    main()
