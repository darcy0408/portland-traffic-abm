"""EXPLORATORY (branch experiment/decay): one run with the LODES-fitted decay scale.

Runs ONE steady-state hour identical to the powell_through reference run (seed 42,
500 vehicles, 30% through-traffic, gravity demand) except for a single knob: the
gravity decay scale is the LODES-fitted 1082 m (calibrate_decay.py, fit A: the
conditional-logit MLE on the within-window LODES OD flows, the like-for-like
calibration for the sim's internal demand) instead of the a-priori 1500 m.

The run gets its own name (powell_through_decayfit) so no saved run is overwritten,
and checkpointing is off (a ~10 s run; also avoids the known stale-checkpoint
hazard of reusing a completed run's name).

The default config is deliberately unchanged: GRAVITY_DECAY_SCALE_M stays 1500 in
config.py, and this script overrides it in memory only. Making the fitted value the
default is a Christof calibration-gate decision.

Run it with:  python src/run_decayfit.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# the single experimental knob: LODES-fitted decay scale (calibrate_decay.py, fit A)
FITTED_DECAY_SCALE_M = 1082.0
RUN_NAME = "powell_through_decayfit"

# everything else must match the powell_through reference run exactly, so any
# difference in the surfaces is attributable to the decay scale alone
assert config.RANDOM_SEED == 42
assert config.N_VEHICLES == 500
assert config.THROUGH_TRAFFIC_FRACTION == 0.30
assert config.DEMAND_GRAVITY and not config.DEMAND_LODES_OD

config.GRAVITY_DECAY_SCALE_M = FITTED_DECAY_SCALE_M
config.RUN_NAME = RUN_NAME

import generate  # noqa: E402  (imported after the overrides; generate reads config at call time)

if __name__ == "__main__":
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    print(f"Run '{RUN_NAME}': gravity decay scale {FITTED_DECAY_SCALE_M:.0f} m "
          f"(LODES-fitted) vs 1500 m a priori; seed {config.RANDOM_SEED}, "
          f"{config.N_VEHICLES} vehicles, "
          f"{config.THROUGH_TRAFFIC_FRACTION:.0%} through-traffic")
    totals, nox, thru = generate.run_simulation(G, use_checkpoint=False)
    generate.save_results(totals, nox, thru)
