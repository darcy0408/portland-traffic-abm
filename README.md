# Portland Traffic ABM

[![CI](https://github.com/darcy0408/portland-traffic-abm/actions/workflows/ci.yml/badge.svg)](https://github.com/darcy0408/portland-traffic-abm/actions/workflows/ci.yml)

Agent-based model of vehicles on Portland's street network, producing per-segment
noise and NO2 estimates that feed a random-forest comparison against published baselines.

## The one rule this structure enforces

Data generation and visualization are kept in separate scripts. The expensive part
(running the simulation) writes its results to disk. The cheap part (drawing figures)
reads those files. This means you can redraw a map, change an axis, or recolor a plot
as many times as you want without ever rerunning the simulation. You will remake
figures often when a paper or the symposium needs them, and you do not want to spend
days regenerating data just to fix a color.

A second rule lives inside the generation script: it checkpoints. If Colab disconnects,
the power goes out, or the machine dies, you resume from the last checkpoint instead of
starting over. On Colab specifically this is not optional, because the local disk is wiped
on every disconnect, so all saved data goes to mounted Google Drive.

## Layout

```
portland-traffic-abm/
  README.md
  config.py              all parameters, the random seed, and every path, in one place
  requirements.txt
  src/
    generate.py          STAGE 1: runs the ABM, checkpoints, saves data. No plotting.
    visualize.py         STAGE 2: reads saved data, writes figures. No simulation.
    checkpoint.py        save and restore simulation state safely
  data/                  created automatically on first run
    network/             the OSMnx street graph, downloaded once and reused
    raw/                 checkpoints and any intermediate state
    processed/           tidy per-segment result tables, ready to plot
  outputs/
    figures/             every generated figure lands here
```

## Workflow

1. Set your parameters in `config.py` (study area, vehicle count, steps, run name).
2. Run `python src/generate.py`. It downloads the network once, runs the simulation,
   checkpoints along the way, and saves a results table to `data/processed/`.
3. Run `python src/visualize.py`. It reads that table and writes a figure to `outputs/figures/`.
4. Tweak the figure and rerun step 3 alone, as often as you like. The simulation does not run again.

To run a new experiment, change `RUN_NAME` in `config.py`. Output files are named after it,
so old runs are never overwritten and you can compare them later.

## Reproducibility notes

- The random seed is set once in `config.py` and applied at the top of `generate.py`,
  so a run with the same config reproduces the same numbers.
- Put this folder on GitHub now, not later. Add comments as you write code, not in a
  cleanup pass that never comes. Every journal and conference will expect public code
  and data, and the habit is far cheaper to keep than to retrofit.

## Colab

In Colab, mount Drive first:

```python
from google.colab import drive
drive.mount('/content/drive')
```

`config.py` detects Colab automatically and points `data/` and `outputs/` at
`MyDrive/PSU REU/abm` so nothing is lost on disconnect.
