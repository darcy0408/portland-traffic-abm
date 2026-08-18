"""Trace each freeway blackspot to the junction that pins it.

The PORTAL speed validation (portal_speed_check.py) found 5 of 91 mainline
stations where the model runs below HALF the real daytime speed, all of them
approaches to major interchanges. The working suspicion is merge starvation:
the kernel has no merge-priority rule, so at a junction where two feeders
compete for one downstream entrance, entry order is arbitrary and one stream
can lock the other out.

This script turns that suspicion into named junctions. Read-only, no
simulation: it reuses portal_speed_check.build() for the station-to-edge
match, then for each blackspot edge

  1. walks DOWNSTREAM along the jammed chain (following occupancy at each
     diverge) until mean speed recovers -- the last jammed edge ends at the
     junction the whole queue is pinned on;
  2. walks UPSTREAM the same way to measure how far the queue reaches back;
  3. prints every in-edge and out-edge at the pin junction with its mean
     speed, stuck share, and throughput, so a starved feeder (jammed, low
     throughput) sitting beside a winning one (moving, high throughput) is
     visible directly.

Usage:  python src/blackspot_trace.py
"""
import sys

import numpy as np

import portal_speed_check as psc

# an edge whose realized mean speed is below this is part of a queue, not flow
JAM_KMH = 30.0
MAX_HOPS = 40          # safety cap on either walk


def edge_meta(G, key):
    """Display metadata for one directed edge."""
    d = G.edges[key]
    nm = d.get("name") or d.get("ref") or "(unnamed)"
    if isinstance(nm, list):
        nm = nm[0]
    hw = d.get("highway")
    if isinstance(hw, list):
        hw = hw[0]
    ln = d.get("lanes")
    if isinstance(ln, list):
        ln = "/".join(str(x) for x in ln)
    return str(nm), str(hw), (str(ln) if ln else "-"), float(d.get("length", 0))


class Stats:
    """Per-seed mean edge stats out of the seed-summed parquet frame."""

    def __init__(self, seg, n_seeds):
        self.seg = seg
        self.n = n_seeds

    def row(self, key):
        if key not in self.seg.index:
            return None
        r = self.seg.loc[key]
        if r["value"] <= 0:
            return None
        return {
            "kmh": 3.6 * r["v_sum"] / r["value"],
            "stuck": r["stuck_sum"] / r["value"],
            "thr": r["throughput"] / self.n,       # vehicles per hour, seed mean
            "veh_s": r["value"] / self.n,          # vehicle-seconds, seed mean
        }

    def jammed(self, key):
        r = self.row(key)
        return r is not None and r["kmh"] < JAM_KMH


def fmt(G, stats, key, mark=" "):
    nm, hw, ln, length = edge_meta(G, key)
    r = stats.row(key)
    if r is None:
        return (f" {mark} {'--':>6}  {'--':>6}  {'--':>7}  {'--':>9}  "
                f"{length:>6.0f}m  ln{ln:<4} {hw:<15} {nm}")
    return (f" {mark} {r['kmh']:>5.1f}k  {100 * r['stuck']:>5.0f}%  "
            f"{r['thr']:>6.0f}/h  {r['veh_s']:>8.0f}vs  "
            f"{length:>6.0f}m  ln{ln:<4} {hw:<15} {nm}")


def next_hop(G, stats, key, downstream=True):
    """The continuation edge with the most occupancy (follow the jam), or None.

    At a diverge the queue's main body sits on whichever branch holds the
    vehicle-time, so occupancy picks the branch the jam actually lives on.
    """
    node = key[1] if downstream else key[0]
    edges = (G.out_edges(node, keys=True) if downstream
             else G.in_edges(node, keys=True))
    best, best_occ = None, 0.0
    for cand in edges:
        if cand == key or (cand[1] == key[0] and cand[0] == key[1]):
            continue                    # no U-turn back onto ourselves
        r = stats.row(cand)
        if r is not None and r["veh_s"] > best_occ:
            best, best_occ = cand, r["veh_s"]
    return best


def walk(G, stats, start, downstream=True):
    """Chain of consecutive jammed edges from `start`, plus the first
    recovered edge past the end (or None if the chain just ends)."""
    chain, key = [start], start
    for _ in range(MAX_HOPS):
        nxt = next_hop(G, stats, key, downstream)
        if nxt is None:
            return chain, None
        if not stats.jammed(nxt):
            return chain, nxt
        chain.append(nxt)
        key = nxt
    return chain, None


def main():
    res, seg, G, n_seeds = psc.build()
    stats = Stats(seg, n_seeds)

    spots = res[res["ratio"] < 0.5].sort_values("ratio")
    print(f"\n{len(spots)} blackspot stations (model below half the real "
          f"daytime speed), traced one by one.")
    print("columns: mean km/h | stuck share | vehicles/hour | vehicle-seconds "
          "| length | lanes tag | class | name\n")

    for _, sp in spots.iterrows():
        start = sp["edge"]
        print("=" * 78)
        print(f"STATION {sp['sid']}: {sp['text']}  [{sp['ref']}]  "
              f"real {sp['day']:.0f} mph vs model {sp['model']:.1f} mph "
              f"(ratio {sp['ratio']:.2f})")

        down, relief = walk(G, stats, start, downstream=True)
        up, _ = walk(G, stats, start, downstream=False)

        # the queue, rear to head: upstream chain reversed, then downstream
        queue = list(reversed(up[1:])) + down
        q_len = sum(edge_meta(G, k)[3] for k in queue)
        print(f"\n  queue chain ({len(queue)} edges, {q_len / 1000:.1f} km; "
              f"S = the station's own edge):")
        for k in queue:
            print(fmt(G, stats, k, mark="S" if k == start else " "))
        if relief is not None:
            print(fmt(G, stats, relief, mark=">"), "   <- first moving edge")

        # the junction the head is pinned on
        head = down[-1]
        node = head[1]
        print(f"\n  PIN JUNCTION = node {node} (end of the last jammed edge)")
        print("  in-edges (feeders competing for entry):")
        for cand in sorted(G.in_edges(node, keys=True),
                           key=lambda c: -(stats.row(c) or {"veh_s": 0})["veh_s"]):
            print(fmt(G, stats, cand, mark="*" if cand == head else " "))
        print("  out-edges (where entry is contested):")
        for cand in G.out_edges(node, keys=True):
            print(fmt(G, stats, cand))
        print()

    # conservation check across all pin junctions: a merge that admits less
    # than its feeders deliver is starving someone.
    print("=" * 78)
    print("done. Read each pin junction: a feeder with high stuck share and")
    print("low vehicles/hour beside one that is moving is the starvation")
    print("signature; balanced feeders point at plain capacity instead.")


if __name__ == "__main__":
    main()
