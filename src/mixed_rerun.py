"""Mixed-fleet corridor reruns (calibration gate G2, set Jul 20).

The mentor approved switching the live sim to the realistic mixed fleet, which
changes every ABSOLUTE NO2/NOx number (~3.76x below all-diesel) while leaving
traffic bit-identical (the class draw uses its own RNG stream). The corridor's
cited numbers (closure percentages C1-C4, day-run D2/D3) therefore need
re-deriving from mixed-fleet runs before they are cited as mixed-fleet values.

This driver reruns the two corridor experiments under the mixed fleet with the
EXACT published corridor configuration (seed 42, 500 vehicles, 1.5 km network,
gravity demand, 30% through-traffic), overridden here at runtime so the committed
config.py can keep the metro defaults. New run names avoid both the stale-
checkpoint trap and clobbering the all-diesel originals.

    python src/mixed_rerun.py closure   # open+closed pair -> powell_mixed_open/_closed
    python src/mixed_rerun.py day       # 24-hour run      -> powell_mixed_day_segments
    python src/mixed_rerun.py report    # READ-ONLY: closure percentages, mixed vs
                                        # the cited all-diesel run, same method as
                                        # closure_robustness.py; plus traffic identity
                                        # checks (mixed traffic must equal powell_through)
    python src/mixed_rerun.py metro     # metro20k under the mixed fleet (committed
                                        # metro config, run name metro20k_mixed, ~30 min).
                                        # Data dirs point at the metro5k-scaleup worktree
                                        # when present (the 20 km caches live there)
    python src/mixed_rerun.py metro-report  # READ-ONLY: metro mixed vs all-diesel
                                            # scale/shape, like fleet_experiment compare

One simulation at a time: each mode runs serially in this one process, and the
sim modes refuse to run if their outputs already exist (delete deliberately to
rerun). After `day`, get the D2/D3 analogs with:
    python src/validate_day.py powell_mixed
"""
import os
import sys

import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

MIXED_BASE = "powell_mixed"        # this driver's run-name base
DIESEL_BASE = "powell_through"     # the cited all-diesel corridor run


def apply_corridor_config():
    """Force the published corridor configuration (the powell_through header) plus
    the mixed fleet. Runtime-only: config.py on disk keeps the metro defaults."""
    config.RUN_NAME = MIXED_BASE
    config.N_VEHICLES = 500
    config.STUDY_RADIUS_M = 1500
    config.DEMAND_LODES_OD = False
    config.THROUGH_TRAFFIC_FRACTION = 0.30
    config.DEMAND_GRAVITY = True
    config.FLEET_MIXED = True
    assert config.RANDOM_SEED == 42, "corridor reproduction is defined at seed 42"
    print(f"corridor config applied: seed {config.RANDOM_SEED}, "
          f"{config.N_VEHICLES} vehicles, {config.THROUGH_TRAFFIC_FRACTION:.0%} "
          f"through-traffic, mixed fleet ON, run base '{MIXED_BASE}'")


def _seg(run):
    return os.path.join(config.PROCESSED_DIR, f"{run}_segments.parquet")


def _refuse_if_exists(*paths):
    for p in paths:
        if os.path.exists(p):
            raise SystemExit(f"{p} already exists. One simulation only: delete it "
                             "deliberately if you truly mean to rerun.")


def run_closure():
    _refuse_if_exists(_seg(f"{MIXED_BASE}_open"), _seg(f"{MIXED_BASE}_closed"))
    apply_corridor_config()
    import generate
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    generate.run_closure_experiment(G)


def run_day():
    day_out = os.path.join(config.PROCESSED_DIR, f"{MIXED_BASE}_day_segments.parquet")
    _refuse_if_exists(day_out)
    apply_corridor_config()
    import generate
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    generate.run_day_experiment(G)


METRO_BASE = "metro20k"            # the cited all-diesel metro run
METRO_MIXED = "metro20k_mixed"     # this driver's metro run name


def apply_metro_dirs():
    """Point the data directories at wherever the 20 km caches live. They were
    built in the metro5k-scaleup worktree (graph, landuse_bg, lodes_od, and every
    metro20k_* result); if that worktree exists, read and write there so the mixed
    run lands beside the all-diesel files it will be compared with. Falls back to
    the default dirs for a future layout where the metro caches live on main."""
    wt = os.path.join(config.BASE_DIR, ".claude", "worktrees", "metro5k-scaleup")
    if not os.path.isdir(os.path.join(wt, "data", "network")):
        # Running from a sibling worktree (BASE_DIR is .claude/worktrees/<x>):
        # the metro caches live next door, not underneath us (Aug 3 fix).
        wt = os.path.join(os.path.dirname(config.BASE_DIR), "metro5k-scaleup")
    if os.path.isdir(os.path.join(wt, "data", "network")):
        config.NETWORK_DIR = os.path.join(wt, "data", "network")
        config.RAW_DIR = os.path.join(wt, "data", "raw")
        config.PROCESSED_DIR = os.path.join(wt, "data", "processed")
        print(f"metro data dirs -> {wt}\\data")
    else:
        print("metro5k-scaleup worktree not found; using default data dirs")


def run_metro():
    """The committed config already IS the metro20k configuration (20 km, 16,500
    vehicles, LODES OD, 15% through-traffic) and FLEET_MIXED defaults True, so the
    only overrides are the run name and the data locations."""
    apply_metro_dirs()
    _refuse_if_exists(_seg(METRO_MIXED))
    config.RUN_NAME = METRO_MIXED
    config.FLEET_MIXED = True
    assert config.RANDOM_SEED == 42 and config.N_VEHICLES == 16500, \
        "expected the committed metro20k configuration"
    import generate
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    totals, nox, thru = generate.run_simulation(G)
    generate.save_results(totals, nox, thru)


def metro_report():
    """Read-only: metro mixed vs all-diesel, the scale/shape questions from
    fleet_experiment.compare at metro scale."""
    import numpy as np
    apply_metro_dirs()
    d = pd.read_parquet(_seg(METRO_BASE))
    m = pd.read_parquet(_seg(METRO_MIXED))
    both = d.merge(m, on=["u", "v", "key"], suffixes=("_d", "_m"))
    assert len(both) == len(d) == len(m), "segment sets differ between runs"
    same = (np.allclose(both["value_d"], both["value_m"])
            and np.allclose(both["throughput_d"], both["throughput_m"]))
    print(f"traffic identical between runs: {same}")
    tot_d, tot_m = both["nox_g_d"].sum(), both["nox_g_m"].sum()
    print(f"network NOx: all-diesel {tot_d:.1f} g, mixed {tot_m:.1f} g, "
          f"ratio {tot_d / tot_m:.2f}x")
    print(f"per vehicle-hour: {tot_d / config.N_VEHICLES:.2f} -> "
          f"{tot_m / config.N_VEHICLES:.2f} g (G6 re-derivation)")
    active = both[(both["nox_g_d"] > 0) & (both["nox_g_m"] > 0)]
    rho = active["nox_g_d"].corr(active["nox_g_m"], method="spearman")
    print(f"per-segment NOx shape agreement ({len(active)} active segments): "
          f"Spearman {rho:.4f}")


def report():
    """Read-only. Closure percentages for the mixed pair beside the cited
    all-diesel pair, computed through the SAME street-matching method the cited
    numbers use (closure_robustness.street_no2 / arterial_total), so any
    difference is the fleet, not the measurement."""
    import osmnx as ox
    from closure_robustness import street_no2, arterial_total, name_of

    G = ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))
    name_by_edge = {(u, v, k): name_of(d)
                    for u, v, k, d in G.edges(keys=True, data=True)}

    print("Closure result, mixed fleet vs the cited all-diesel run "
          "(corridor, seed 42, same demand/network)\n")

    pcts = {}
    for label, base in (("all-diesel", DIESEL_BASE), ("mixed", MIXED_BASE)):
        o = pd.read_parquet(_seg(f"{base}_open"))
        c = pd.read_parquet(_seg(f"{base}_closed"))
        so, sc = street_no2(o, name_by_edge), street_no2(c, name_by_edge)
        row = {}
        for a in ("Powell", "Division", "Holgate"):
            ot, ct = arterial_total(so, a), arterial_total(sc, a)
            row[a] = 100 * (ct - ot) / ot
        row["network"] = 100 * (sc["__NETWORK__"] - so["__NETWORK__"]) / so["__NETWORK__"]
        row["open NO2 g"] = so["__NETWORK__"]
        pcts[label] = row

    hdr = f"{'':<12}" + "".join(f"{a:>12}" for a in
                                ("Powell", "Division", "Holgate", "network"))
    print(hdr + f"{'open NO2 g':>14}")
    for label, row in pcts.items():
        line = f"{label:<12}" + "".join(f"{row[a]:>+11.1f}%" for a in
                                        ("Powell", "Division", "Holgate", "network"))
        print(line + f"{row['open NO2 g']:>14.1f}")

    # traffic identity: the mixed pair must carry the SAME traffic as the diesel
    # pair (fleet draws use their own RNG stream), otherwise the comparison above
    # confounds fleet chemistry with changed routing.
    import numpy as np
    for half in ("open", "closed"):
        d = pd.read_parquet(_seg(f"{DIESEL_BASE}_{half}"))
        m = pd.read_parquet(_seg(f"{MIXED_BASE}_{half}"))
        both = d.merge(m, on=["u", "v", "key"], suffixes=("_d", "_m"))
        same = (len(both) == len(d) == len(m)
                and np.allclose(both["value_d"], both["value_m"])
                and np.allclose(both["throughput_d"], both["throughput_m"]))
        print(f"traffic identical to {DIESEL_BASE}_{half}: {same}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    if mode == "closure":
        run_closure()
    elif mode == "day":
        run_day()
    elif mode == "report":
        report()
    elif mode == "metro":
        run_metro()
    elif mode == "metro-report":
        metro_report()
    else:
        raise SystemExit(__doc__)
