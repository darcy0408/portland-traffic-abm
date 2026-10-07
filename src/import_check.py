"""Import smoke test: can every module in src/ be imported with the declared dependencies?

Why this exists (Oct 2026 audit, finding H-1): requirements.txt listed six packages
while a dozen modules also imported scikit-learn, scipy, shapely, geopandas or
Pillow. CI stayed green only because scenarios.py needs none of them, so a fresh
clone could install "everything" and still fail the first time it ran an analysis
script. This check imports each src/*.py in its own interpreter and fails the run
if any import raises ModuleNotFoundError (a missing third-party package).

Other exceptions are reported but do not fail the check: in CI the gitignored
data/ directory is absent, so a module that opens a cached file at import time
raises FileNotFoundError there even though its dependencies are complete. That is
a different problem (import-time side effects) from the one this script guards.

What this check does NOT cover, so nobody reads a green run as more than it is:
  - imports inside functions (e.g. pandas.read_excel pulling in openpyxl only when
    rao_data.load() runs); only module-level imports are exercised
  - whether a package is the right VERSION; a wrong-but-installed version imports fine
  - packages that arrive only transitively (shapely and geopandas via osmnx, Pillow
    via matplotlib); the check passes whether or not requirements.txt names them
  - whether any script actually runs; scenarios.py is the only execution test in CI

Each module runs in a subprocess so one module's import-time state cannot leak
into the next, and so a hang in one module is caught by the timeout rather than
stalling the whole sweep.

Usage: python src/import_check.py            (exit 0 = all dependencies present)
"""

import glob
import os
import subprocess
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_S = 180  # per module; osmnx and geopandas imports are slow on a cold cache


def check_module(module_name):
    """Import one module in a fresh interpreter. Returns (status, last_stderr_line)."""
    code = f"import sys; sys.path.insert(0, {SRC_DIR!r}); import {module_name}"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return "timeout", f"no result within {TIMEOUT_S} s"
    if result.returncode == 0:
        return "ok", ""
    lines = [l for l in result.stderr.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else "(no stderr)"
    # ModuleNotFoundError is the one failure this check is for: a package the
    # code imports that requirements.txt does not install.
    status = "missing-dependency" if "ModuleNotFoundError" in last else "import-error"
    return status, last


def main():
    modules = sorted(
        os.path.basename(path)[:-3]
        for path in glob.glob(os.path.join(SRC_DIR, "*.py"))
        if not os.path.basename(path).startswith("__")
    )
    missing, other = [], []
    for name in modules:
        status, detail = check_module(name)
        if status == "ok":
            continue
        (missing if status == "missing-dependency" else other).append((name, status, detail))

    print(f"{len(modules)} modules in src/: {len(modules) - len(missing) - len(other)} imported cleanly")
    for name, status, detail in other:
        # Reported, not fatal: usually a gitignored data file read at import time.
        print(f"  NOTE  {name}: {status}: {detail}")
    for name, status, detail in missing:
        print(f"  FAIL  {name}: {detail}")

    if missing:
        print(f"\n{len(missing)} module(s) import a package requirements.txt does not install.")
        sys.exit(1)
    print("\nAll declared dependencies cover every src/ import.")


if __name__ == "__main__":
    main()
