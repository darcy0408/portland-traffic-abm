"""THE TWO SURFACES RANK STREETS DIFFERENTLY: the figure version of ledger section 14.

The claim on the slide (and the one-story pitch to Christof): the same I-205
closure, scored on NO2 and on noise, agrees on DIRECTION almost everywhere and
disagrees on WHICH STREETS MATTER. A quiet street absorbing detour traffic is a
large acoustic event and a small chemical one; a busy arterial absorbing the same
detour is the reverse. So a mitigation priority list read off one surface is not
the list you get off the other, which is what no single-surface model can express.

A slopegraph is the right form for exactly that claim: each street is one line
between its rank on the NO2 surface and its rank on the noise surface, and the
argument is literally the crossing lines. A bar chart of either surface alone
cannot show it.

Read-only, no simulation: reuses src/freeway_noise_contrast.py end to end (same
24 saved fwms parquets, same paired 8-seed design, same pre-set bar, same
verified-identical vectorized CNOSSOS), so the figure and the ledger table cannot
diverge by construction. Per-street statistics are cached to JSON on first run
because collecting them reads 24 parquets against a 159,425-edge graph; --refresh
recomputes.

REPRODUCTION GATE (same pattern as demos/upstream_shadow_map.py): before
rendering, the script checks the recomputed statistics against ledger values
FW10, FW11 and FW12, including the rank positions the ledger quotes. If anything
drifts it aborts without writing the figure.

WHAT THIS FIGURE MAY NOT BE USED TO SAY (ledger section 14 caveats):
  - Not audibility. A SUPPORTED verdict means reliably nonzero across seeds;
    ~3 dB is roughly where a change becomes noticeable. Only the Abernethy arm's
    headline streets clear that. Say "the surfaces rank streets differently",
    never "audible change at the Powell stretch".
  - Not magnitudes. The campaign ran the base model (MOBIL/LANES/WEBSTER off,
    flag F6), which bites the noise column hardest. Direction and rank only.
  - The dB values are paired differences of SOURCE levels. No absolute dB.

Usage:  python demos/no2_vs_noise_ranks.py [--refresh] [--realism]
Writes: outputs/figures/no2_vs_noise_ranks.png            (base campaign)
        outputs/figures/no2_vs_noise_ranks_realism.png    (--realism)

--realism draws the same figure from the F6 realism campaign (fwmsr, ledger
section 16, IDs FR8-FR10) with its own cache, its own gate, and its own output
file, so the base figure stays reproducible beside it. The realism version is
the citable one: quote FR8-FR10, never FW10-FW12 (graveyarded Aug 2).
"""
import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
from scipy.stats import spearmanr

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(_ROOT)
sys.path.append(os.path.join(_ROOT, "src"))

import config
import freeway_multiseed as fms
import freeway_noise_contrast as fnc

CACHE = os.path.join(config.PROCESSED_DIR, "fw_no2_noise_contrast_stats.json")
CACHE_REALISM = os.path.join(config.PROCESSED_DIR,
                             "fw_no2_noise_contrast_stats_realism.json")

# Ledger FW10/FW11 (mean dNO2 g, mean dNoise dB, rank by NO2, rank by dB) and
# FW12 (SUPPORTED-only Spearman, street count). Ranks are over the near-field
# streets carrying a finite dB pair, which is the set the ledger ranked.
GATE = {
    "abernethy": {
        "streets": {
            "McLoughlin Boulevard": (266.6, 3.47, 1, 3),
            "Main Street": (195.5, 6.84, 2, 2),
            "Moss Street": (37.6, 9.74, 4, 1),
        },
        "rho": (0.729, 27),
    },
    "powell": {
        "streets": {
            "Southeast Division Street": (62.5, 0.38, 2, None),
            "Southeast 82nd Avenue": (10.2, 1.61, 4, 1),
        },
        "rho": (0.461, 15),
    },
}

# Ledger section 16 (FR8/FR9/FR10), the realism-campaign re-score. Same tuple
# shape. The ramps' sign-flip rows (NO2 up, noise DOWN, both supported) are the
# section's headline and are pinned here so the figure cannot drift off them.
GATE_REALISM = {
    "abernethy": {
        "streets": {
            "McLoughlin Boulevard": (720.5, 5.29, 1, 3),
            "Main Street": (269.3, 7.93, 2, 2),
            "Moss Street": (28.2, 8.78, 6, 1),
            "(unnamed)": (104.4, -2.02, 4, None),
        },
        "rho": (0.338, 40),
    },
    "powell": {
        "streets": {
            "(unnamed)": (929.1, -0.20, 1, None),
            "Southeast Division Street": (67.6, 0.35, 2, None),
            "Southeast 82nd Avenue": (11.2, 1.58, 4, 1),
        },
        "rho": (0.500, 16),
    },
}

# Deck dark-theme identity (matches demos/upstream_shadow_map.py).
BG = "#0d1117"
INK = "#e6edf3"
MUTED = "#9da7b3"
GRID = "#39424e"
NOISE_UP = "#f0a35e"     # ranks higher on noise than on NO2: the acoustic surprise
NO2_UP = "#5eb0f0"       # ranks higher on NO2 than on noise
FLAT = "#6b7684"         # ranks roughly agree

N_SHOW = 6               # top-N by each surface; the figure draws their union


def compute():
    """Per-street paired means for both arms, via the ledgered pipeline."""
    if not fnc.verify_vectorized():
        raise SystemExit("vectorized CNOSSOS disagrees with noise.py; refusing to run")
    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    geo = fnc.load_geo(G)

    out = {}
    for arm in fnc.ARMS:
        per_seed, used = fnc.collect(arm, geo)
        streets = []
        for nm, v in per_seed.items():
            if len(v) != used:          # same completeness filter as the report
                continue
            dg = np.array([x[0] for x in v])
            ddb = np.array([x[2] for x in v])
            finite = ddb[np.isfinite(ddb)]
            n = len(dg)
            vg, _ = fnc.verdict(dg.mean(), dg.std(ddof=1) if n > 1 else 0.0,
                                n, int((dg > 0).sum()))
            # noise verdict only with a finite dB pair in EVERY seed, matching the
            # report: the unanimity bar's p-value assumes the full seed set
            if len(finite) == n:
                vn, _ = fnc.verdict(finite.mean(), finite.std(ddof=1),
                                    len(finite), int((finite > 0).sum()))
                d_db = float(finite.mean())
            else:
                vn, d_db = f"on/off {len(finite)}/{n}", None
            streets.append({"name": nm, "d_no2": float(dg.mean()), "d_db": d_db,
                            "no2_supported": vg == "SUPPORTED",
                            "noise_supported": vn == "SUPPORTED"})
        out[arm] = {"seeds": used, "streets": streets}
    return out


def load(refresh=False, realism=False):
    cache = CACHE_REALISM if realism else CACHE
    if not refresh and os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)
    data = compute()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    with open(cache, "w") as fh:
        json.dump(data, fh, indent=1)
    return data


def ranked_sets(arm_data):
    """The two ranked sets section 14 uses.

    `ranked`  : every near-field street with a finite dB pair. This is what the
                ledger's rank positions (Moss 4th by NO2, 1st by dB) count over.
    `sup`     : the subset SUPPORTED on either surface. This is what the cited
                Spearman counts over, because chaos is CORRELATED between the two
                surfaces and the all-streets value mixes physics with that.
    """
    ranked = [s for s in arm_data["streets"] if s["d_db"] is not None]
    sup = [s for s in ranked if s["no2_supported"] or s["noise_supported"]]
    by_no2 = sorted(ranked, key=lambda s: -s["d_no2"])
    by_db = sorted(ranked, key=lambda s: -s["d_db"])
    rank_no2 = {s["name"]: i + 1 for i, s in enumerate(by_no2)}
    rank_db = {s["name"]: i + 1 for i, s in enumerate(by_db)}
    return ranked, sup, rank_no2, rank_db


def check_gate(data, gate):
    """Abort before rendering if anything drifted from the ledger."""
    for arm, spec in gate.items():
        ranked, sup, rank_no2, rank_db = ranked_sets(data[arm])
        by_name = {s["name"]: s for s in ranked}
        for nm, (g, db, r_g, r_db) in spec["streets"].items():
            if nm not in by_name:
                raise SystemExit(f"GATE: {arm}: street '{nm}' missing")
            s = by_name[nm]
            if abs(s["d_no2"] - g) > 0.1:
                raise SystemExit(
                    f"GATE: {arm}/{nm} dNO2 {s['d_no2']:.1f} != ledger {g}")
            if abs(s["d_db"] - db) > 0.01:
                raise SystemExit(
                    f"GATE: {arm}/{nm} dNoise {s['d_db']:.2f} != ledger {db}")
            if rank_no2[nm] != r_g:
                raise SystemExit(
                    f"GATE: {arm}/{nm} NO2 rank {rank_no2[nm]} != ledger {r_g}")
            if r_db is not None and rank_db[nm] != r_db:
                raise SystemExit(
                    f"GATE: {arm}/{nm} noise rank {rank_db[nm]} != ledger {r_db}")
        rho_l, n_l = spec["rho"]
        rho = spearmanr([s["d_no2"] for s in sup], [s["d_db"] for s in sup]).statistic
        if len(sup) != n_l:
            raise SystemExit(
                f"GATE: {arm}: {len(sup)} SUPPORTED-only streets != ledger {n_l}")
        if abs(rho - rho_l) > 0.001:
            raise SystemExit(f"GATE: {arm}: Spearman {rho:+.3f} != ledger {rho_l:+.3f}")
        print(f"  gate OK  {arm}: {len(spec['streets'])} street values and ranks, "
              f"Spearman {rho:+.3f} over {len(sup)} streets")


def fmt_g(x):
    """Grams, with a decimal only where rounding to whole grams would print '+0'."""
    return f"{x:+,.0f} g" if abs(x) >= 10 else f"{x:+.1f} g"


def display_label(name):
    """Shorten OSM's full names for slide legibility; flag the pooled ramps."""
    if name == "(unnamed)":
        return "I-205 ramps (unnamed)"
    out = name.replace("Southeast ", "SE ").replace("Northeast ", "NE ")
    return out.replace(" Boulevard", " Blvd").replace(" Avenue", " Ave")


def panel(ax, arm, data, title):
    ranked, sup, rank_no2, rank_db = ranked_sets(data[arm])
    rho = spearmanr([s["d_no2"] for s in sup], [s["d_db"] for s in sup]).statistic

    # Draw ONLY streets that clear the pre-set bar on at least one surface, which is
    # the same subset the quoted Spearman is computed over. Ranking the full set here
    # would put chaos streets on the slide (at the Powell arm, three of the top six by
    # dB are streets whose change is not distinguishable from seed noise) while the
    # caption underneath quoted a statistic that deliberately excludes them.
    by_no2 = sorted(sup, key=lambda s: -s["d_no2"])
    by_db = sorted(sup, key=lambda s: -s["d_db"])
    show = {s["name"] for s in by_no2[:N_SHOW]} | {s["name"] for s in by_db[:N_SHOW]}

    # Plot against DISPLAY position (the union set, re-ranked 1..n on each side) so
    # the panel stays readable, and print the TRUE rank out of the full near-field
    # set beside each label so nothing is overstated by the compression.
    shown_no2 = [s for s in by_no2 if s["name"] in show]
    shown_db = [s for s in by_db if s["name"] in show]
    pos_l = {s["name"]: i for i, s in enumerate(shown_no2)}
    pos_r = {s["name"]: i for i, s in enumerate(shown_db)}

    xl, xr = 0.0, 1.0
    for nm in show:
        yl, yr = pos_l[nm], pos_r[nm]
        moved = rank_no2[nm] - rank_db[nm]      # positive: better on noise
        color = NOISE_UP if moved >= 2 else NO2_UP if moved <= -2 else FLAT
        lw = 2.6 if abs(moved) >= 2 else 1.4
        ax.plot([xl, xr], [yl, yr], color=color, lw=lw, alpha=0.95,
                solid_capstyle="round", zorder=2)
        ax.scatter([xl, xr], [yl, yr], s=26, color=color, zorder=3)

    for s in shown_no2:
        nm = s["name"]
        ax.text(xl - 0.045, pos_l[nm],
                f"{display_label(nm)}  {fmt_g(s['d_no2'])}",
                ha="right", va="center", fontsize=9.5, color=INK)
        ax.text(xl - 0.045, pos_l[nm] + 0.34, f"#{rank_no2[nm]} of {len(ranked)}",
                ha="right", va="center", fontsize=7.2, color=MUTED)
    for s in shown_db:
        nm = s["name"]
        ax.text(xr + 0.045, pos_r[nm],
                f"{s['d_db']:+.2f} dB  {display_label(nm)}",
                ha="left", va="center", fontsize=9.5, color=INK)
        ax.text(xr + 0.045, pos_r[nm] + 0.34, f"#{rank_db[nm]} of {len(ranked)}",
                ha="left", va="center", fontsize=7.2, color=MUTED)

    ax.set_title(title, color=INK, fontsize=12.5, pad=16, loc="center")
    ax.text(xl, -0.85, "ranked by added NO2", ha="center", va="center",
            fontsize=10, color=MUTED, style="italic")
    ax.text(xr, -0.85, "ranked by added noise", ha="center", va="center",
            fontsize=10, color=MUTED, style="italic")
    ax.text(0.5, len(show) - 0.15,
            f"rank agreement over the {len(sup)} streets that clear the bar: "
            f"Spearman {rho:+.3f}",
            ha="center", va="center", fontsize=9, color=MUTED)

    ax.set_xlim(-0.72, 1.72)
    ax.set_ylim(len(show) + 0.15, -1.35)     # rank 1 at the top
    ax.axis("off")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true",
                    help="recompute the per-street statistics instead of using the cache")
    ap.add_argument("--realism", action="store_true",
                    help="draw from the F6 realism campaign (fwmsr, ledger section 16)")
    a = ap.parse_args()

    if a.realism:
        # the harness's own switch; fnc.collect/run_name read these at call time
        fms.PREFIX = "fwmsr"
        fms.STACK_REALISM = True

    data = load(a.refresh, a.realism)
    if a.realism:
        print("checking against ledger section 16 (FR8, FR9, FR10):")
        check_gate(data, GATE_REALISM)
    else:
        print("checking against ledger section 14 (FW10, FW11, FW12):")
        check_gate(data, GATE)

    fig, axes = plt.subplots(1, 2, figsize=(15.5, 7.2), facecolor=BG)
    for ax in axes:
        ax.set_facecolor(BG)

    n_seeds = data["abernethy"]["seeds"]
    panel(axes[0], "abernethy", data,
          "Abernethy Bridge closed\n(I-205, 15 km out)")
    panel(axes[1], "powell", data,
          "I-205 at the Powell stretch closed\n(5.7 km out)")

    fig.suptitle("The same closure, scored two ways: the surfaces disagree on "
                 "which streets matter",
                 color=INK, fontsize=16, y=0.968)
    stack_note = ("full realism stack (lane changing, heterogeneity, signals)"
                  if a.realism else "base model")
    fig.text(0.5, 0.906,
             f"Paired {n_seeds}-seed I-205 closure, streets within 2 km, "
             f"{stack_note}. "
             "Orange = ranks higher on noise than on NO2; blue = the reverse.",
             ha="center", color=MUTED, fontsize=10.5)
    if a.realism:
        footer = ("Ledger section 16 (FR8-FR10), realism campaign (F6 resolved). "
                  "Statistical support is not audibility (~3 dB is noticeable; "
                  "nothing at the Powell stretch reaches it). No absolute dB: "
                  "paired source-level differences only.")
    else:
        footer = ("Ledger section 14 (FW10-FW12), SUPERSEDED by section 16. "
                  "Direction and rank only: base model (flag F6), and statistical "
                  "support is not audibility "
                  "(~3 dB is noticeable; nothing at the Powell stretch reaches it).")
    fig.text(0.5, 0.028, footer, ha="center", color=MUTED, fontsize=8.5)

    out = os.path.join(config.FIGURES_DIR,
                       "no2_vs_noise_ranks_realism.png" if a.realism
                       else "no2_vs_noise_ranks.png")
    os.makedirs(config.FIGURES_DIR, exist_ok=True)
    fig.subplots_adjust(left=0.13, right=0.87, top=0.800, bottom=0.075, wspace=0.62)
    fig.savefig(out, dpi=200, facecolor=BG)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
