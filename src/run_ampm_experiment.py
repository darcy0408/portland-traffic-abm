"""Run the directional AM/PM commute day experiment (worktree experiment/ampm).

EXPLORATORY. This runner exists so the experiment's exact settings are committed
and reproducible without changing the config.py defaults that the main runs
(powell_through, powell_no2_day) depend on. It overrides only two values in the
imported config module, then runs the standard `day` experiment once:

  RUN_NAME           = "powell_day_ampm"   (distinct output files, nothing overwritten)
  DEMAND_DIRECTIONAL = True                (AM home->work, PM reversed; config.py)

Everything else is the committed config: seed 42, N_VEHICLES 500 daily average,
THROUGH_TRAFFIC_FRACTION 0.30, gravity demand with the 1.5 km decay scale.

Run it with:  python src/run_ampm_experiment.py
Then analyze: python src/analyze_ampm.py
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

# Override BEFORE importing generate so every read of config.* in the run sees the
# experiment settings. config is a module singleton, so generate shares this state.
config.RUN_NAME = "powell_day_ampm"
config.DEMAND_DIRECTIONAL = True

import generate

if __name__ == "__main__":
    print(f"AM/PM directional day experiment: RUN_NAME={config.RUN_NAME}, "
          f"seed={config.RANDOM_SEED}, through={config.THROUGH_TRAFFIC_FRACTION}, "
          f"directional={config.DEMAND_DIRECTIONAL}")
    generate.set_seeds(config.RANDOM_SEED)
    G = generate.get_network()
    generate.run_day_experiment(G)
