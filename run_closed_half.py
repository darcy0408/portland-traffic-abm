"""One-off driver: run ONLY the closed half of the metro20k closure experiment.

Why this exists: the combined `python src/generate.py closure` run was killed
twice by machine-side stops (Jul 13 and Jul 14, 2026). The second attempt got
the OPEN half saved (metro20k_open_segments.parquet, total NOx 645737.8 g)
before dying early in the closed half. Rerunning the combined mode would waste
the finished open half, so this driver runs just the missing closed half.

Two deliberate differences from run_closure_experiment in generate.py:
- Checkpointing is ON. Closure mode turns it off because corridor-scale halves
  took ~10 s; at metro scale a half is ~25 min and this run keeps getting
  killed. RUN_NAME is set to metro20k_closed before simulating, so the
  checkpoint file is its own (metro20k_closed_checkpoint.pkl) and a kill
  resumes instead of restarting.
- The checkpoint is deleted after a successful save, so a future rerun can
  never silently resume from a completed run (the stale-checkpoint trap noted
  in the Jul 4 audit).

Demand pairing with the open half is preserved: run_simulation() seeds a fresh
RNG stream from config.RANDOM_SEED at the START of every call, so this closed
half draws the exact same origins/destinations the open half drew, same as the
two halves of the combined mode. Any surface difference is the closure, not
randomness.

Run from the metro5k-scaleup worktree root:
    python -u run_closed_half.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import config
import generate
from checkpoint import checkpoint_path

generate.set_seeds(config.RANDOM_SEED)          # mirrors generate.py main()
G = generate.get_network()

base = config.RUN_NAME                          # metro20k
open_file = os.path.join(config.PROCESSED_DIR, f"{base}_open_segments.parquet")
if not os.path.exists(open_file):
    raise SystemExit(f"Open half missing ({open_file}); run the full closure mode instead.")

Gc = G.copy()
removed = generate.apply_closure(Gc)
lat, lon, r = config.CLOSURE
print(f"[closed] removed {len(removed)} segments within {r:.0f} m of ({lat}, {lon})")

config.RUN_NAME = f"{base}_closed"
totals, nox, thru = generate.run_simulation(Gc, use_checkpoint=True)
generate.save_results(totals, nox, thru)

# a completed run's checkpoint must not survive to silently serve a rerun
ckpt = checkpoint_path(config.RAW_DIR, config.RUN_NAME)
if os.path.exists(ckpt):
    os.remove(ckpt)
    print(f"cleared completed-run checkpoint {ckpt}")

closed_no2 = config.F_NO2 * sum(nox.values())
print(f"closed-network total NO2: {closed_no2:.1f} g")
print("Both halves saved; compare with visualize.py closure "
      "(reads metro20k_open / metro20k_closed).")
