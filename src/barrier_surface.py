"""Barrier-aware noise contrast: the Rose Quarter closure, open vs closed.

The prediction this script banks, dated before the Sept 11 closure: I-5 traffic
through the Rose Quarter sits behind ODOT sound walls, and its detour routes
mostly do not. So when the closure moves traffic off the freeway and onto the
parallels, a barrier-aware model and a barrier-blind model disagree in a
specific, testable way: the blind model overstates how much relief the closure
brings to wall-shielded blocks (it thinks the freeway was loud there, but the
wall had already eaten much of that noise), while both models agree the noise
increase lands on the unshielded detour corridors. The wedge between the two
models is the walls' fingerprint on the closure.

What it computes, for each of 1,003 block-group population centroids:
  1. Every road segment with flow becomes a line of point sources (one per
     SRC_STEP_M along its geometry). Each point emits the CNOSSOS category-1
     octave-band energy per metre (src/noise.py, verified against Directive
     (EU) 2015/996) times its share of the segment, at the run's own
     congestion-aware speed (v = L * throughput / value).
  2. Each source-receiver path within CUTOFF_M gets spherical spreading and,
     where an ODOT wall line (step 1) crosses the path, the Maekawa band
     insertion loss (src/barrier_physics.py, step 2, calibrated against ODOT's
     own attenuation numbers). Single most effective wall per path, finite
     wall length respected, all in the energy domain.
  3. Receiver energy = sum over sources. Four totals per receiver per seed:
     {open, closed} x {with walls, barrier-blind}.
  4. Across the 8 paired seeds (the chaos-floor rule: closure differences are
     only claimed paired): per-receiver median dB change, seed sign agreement,
     the barrier wedge (with-walls change minus blind change), and the
     receiver's current wall shielding.

Discipline carried over from freeway_noise_contrast.py: everything combines in
the energy domain, dB are never summed or averaged, silent segments are zero
energy not dropped, and the levels are SOURCE-side (spreading only, no ground
or air absorption), so no absolute dB from this script is ever citable. Only
paired differences are reported.

The propagation geometry differs from the per-segment surface in noise.py on
purpose: noise.py stands one receiver 10 m from each segment (cylindrical
spreading, a roadside level), while a block-group centroid hears MANY roads at
hundreds of metres, so here each discretized point spreads spherically and the
receiver sums them. That is the same line-of-point-sources construction the
step-2 calibration used, the one that reproduced ODOT's measured first-row
attenuations (median bias -0.2 dB at 15 m).

Reads only saved files (fwrqn parquets, the step-1 wall lines, the prereg
metro20k graph, landuse_bg.parquet); runs no simulation. The slow geometry
(source points, pairs, wall transmissions) is cached to
data/processed/barrier_pairs.npz and reused, since it is identical for all 16
runs; delete the cache or pass --rebuild-pairs after changing walls or
constants.

Usage:  python src/barrier_surface.py [--rebuild-pairs]
Writes: data/processed/barrier_surface_bg.parquet   per-receiver stats
        outputs/figures/barrier_surface_maps.png    maps + wedge scatter
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import barriers                     # DEFAULT_GRAPH + the prereg md5 guard
import barrier_physics as bp
import noise

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WALLS_PARQUET = os.path.join(BASE, "data", "processed", "odot_walls_lines.parquet")
PAIRS_CACHE = os.path.join(BASE, "data", "processed", "barrier_pairs.npz")
OUT_PARQUET = os.path.join(BASE, "data", "processed", "barrier_surface_bg.parquet")
OUT_FIG = os.path.join(BASE, "outputs", "figures", "barrier_surface_maps.png")

# the fwrqn campaign (non-work demand, mixed fleet, 16,500 vehicles) ran on the
# exact prereg metro20k graph, so the step-1 wall lines align with it directly
FWRQN_DIR = "C:/dev/pta-realism/data/processed"
RECEIVERS_PARQUET = os.path.join(BASE, "..", "freeway-closure", "data",
                                 "processed", "landuse_bg.parquet")
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]      # the paired closure seeds
ARMS = ("open", "rosequarter")

SRC_STEP_M = 25.0     # point-source spacing along each segment
CUTOFF_M = 1500.0     # sources beyond this do not reach the receiver sum; the
                      # 1/d^2 tail is negligible against in-cutoff arterials,
                      # and the cutoff is identical in both arms so paired
                      # differences are unbiased by it
MIN_DIST_M = 10.0     # distance floor for a centroid sitting on a road
GRID_M = 500.0        # spatial-hash cell size for the pair build
MIN_VALID_SEEDS = 6   # a receiver needs this many valid paired seeds to report

# Cap on the RECOVERED speed. v = L * throughput / value explodes on a few
# very short segments (2 to 9 m) because vehicle-seconds are credited to the
# segment a car starts its step on, the Jul 4 known limitation. Uncapped, one
# 2 m segment at a recovered 658 km/h carried 84% of a run's source energy
# (CNOSSOS rolling power grows steeply with speed). 130 km/h is the upper end
# of the CNOSSOS category-1 validity range, the mirror of the V_FLOOR_KPH
# rule already in noise.py; 16 to 18 segments per run hit it.
V_CAP_KPH = 130.0

# the Rose Quarter zoom window for the figure, lon/lat
ZOOM = (-122.70, -122.64, 45.50, 45.56)


# --- vectorized physics ------------------------------------------------------
# barrier_physics.py is scalar per path (right for the calibration's ~700
# walls); here there are millions of paths, so the same math runs on arrays and
# is verified element-by-element against the scalar reference before use, the
# same discipline freeway_noise_contrast.py applied to its vectorized CNOSSOS.

def best_delta_vec(sxy, rx, ry, walls_xy, walls_h, sh, rh):
    """Signed path-length difference of the single most effective wall for each
    source in sxy (n, 2) to one receiver. Returns (n,) with -inf where no wall
    crosses the path (mirrors barrier_band_il's best-delta rule)."""
    sx, sy = sxy[:, 0:1], sxy[:, 1:2]                       # (n, 1)
    dx, dy = rx - sx, ry - sy
    wx0, wy0 = walls_xy[None, :, 0], walls_xy[None, :, 1]   # (1, m)
    ex = walls_xy[None, :, 2] - wx0
    ey = walls_xy[None, :, 3] - wy0
    denom = dx * ey - dy * ex                               # (n, m)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = ((wx0 - sx) * ey - (wy0 - sy) * ex) / denom
        u = ((wx0 - sx) * dy - (wy0 - sy) * dx) / denom
    hit = (np.abs(denom) > 1e-12) & (t > 0.0) & (t < 1.0) & (u >= 0.0) & (u <= 1.0)
    ix, iy = sx + t * dx, sy + t * dy
    d1 = np.hypot(ix - sx, iy - sy)
    d2 = np.hypot(rx - ix, ry - iy)
    dsr = d1 + d2
    wh = walls_h[None, :]
    a = np.hypot(d1, wh - sh)
    b = np.hypot(d2, wh - rh)
    d = np.hypot(dsr, rh - sh)
    delta = a + b - d
    with np.errstate(invalid="ignore"):
        los = sh + (rh - sh) * (d1 / dsr)
    delta = np.where(wh >= los, delta, -delta)
    delta = np.where(hit, delta, -np.inf)
    return delta.max(axis=1)


def kurze_anderson_il_vec(delta_m):
    """kurze_anderson_il for an array of deltas: (k,) -> (k, 8) band IL."""
    n = 2.0 * np.asarray(delta_m, dtype=float)[:, None] \
        * noise.OCTAVE_BANDS_HZ[None, :] / bp.C_SOUND_MS
    il = np.zeros_like(n)
    pos = n > 1e-9
    x = np.sqrt(2.0 * np.pi * n[pos])
    il[pos] = 5.0 + 20.0 * np.log10(x / np.tanh(x))
    trans = (n <= 1e-9) & (n > -0.2)
    x = np.sqrt(2.0 * np.pi * np.abs(n[trans]))
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(x > 1e-9, x / np.tan(x), 1.0)
    il[trans] = np.maximum(5.0 + 20.0 * np.log10(v), 0.0)
    return np.clip(il, 0.0, bp.IL_CAP_DB)


def band_energy_per_m(q_vph, v_kph):
    """Linear A-weighted octave-band energy per metre of road for arrays of
    flow and TRUE mean speed. Vectorizes noise.segment_line_power_dba but stays
    in bands (the wall transmission is band-dependent). Zero where no flow."""
    q = np.asarray(q_vph, dtype=float)
    v = np.asarray(v_kph, dtype=float)
    ok = (q > 0) & (v > 0) & np.isfinite(v)
    v_src = np.maximum(np.where(ok, v, noise.V_REF_KPH), noise.V_FLOOR_KPH)[:, None]
    lwr = noise.AR_CAT1 + noise.BR_CAT1 * np.log10(v_src / noise.V_REF_KPH)
    lwp = noise.AP_CAT1 + noise.BP_CAT1 * (v_src - noise.V_REF_KPH) / noise.V_REF_KPH
    lw_band = 10.0 * np.log10(10.0 ** (lwr / 10.0) + 10.0 ** (lwp / 10.0))
    w = 10.0 ** ((lw_band + noise.A_WEIGHTING_DB) / 10.0)
    flow = np.where(ok, q / (1000.0 * np.where(ok, v, 1.0)), 0.0)
    return w * flow[:, None]


def verify_vectorized(walls_xy, walls_h, rng):
    """Check both vectorized paths against the scalar references."""
    # CNOSSOS bands vs noise.segment_line_power_dba on random flow/speed
    q = rng.uniform(1, 2000, 200)
    v = rng.uniform(3, 120, 200)
    w = band_energy_per_m(q, v)
    ours = 10.0 * np.log10(w.sum(axis=1))
    ref = np.array([noise.segment_line_power_dba(qi, vi) for qi, vi in zip(q, v)])
    assert np.allclose(ours, ref, atol=1e-9), "vectorized CNOSSOS mismatch"

    # wall IL vs barrier_band_il on random paths near random walls
    n_checked = 0
    for _ in range(2000):
        i = rng.integers(len(walls_h))
        mx = (walls_xy[i, 0] + walls_xy[i, 2]) / 2.0
        my = (walls_xy[i, 1] + walls_xy[i, 3]) / 2.0
        sxy = np.array([[mx + rng.uniform(-300, 300), my + rng.uniform(-300, 300)]])
        rx, ry = mx + rng.uniform(-300, 300), my + rng.uniform(-300, 300)
        ref_il = bp.barrier_band_il(sxy[0, 0], sxy[0, 1], rx, ry,
                                    walls_xy, walls_h)
        best = best_delta_vec(sxy, rx, ry, walls_xy, walls_h,
                              bp.SOURCE_H_M, bp.RECEIVER_H_M)[0]
        our_il = (kurze_anderson_il_vec(np.array([best]))[0]
                  if np.isfinite(best) else np.zeros(8))
        assert np.allclose(our_il, ref_il, atol=1e-9), "vectorized IL mismatch"
        n_checked += int(np.isfinite(best))
    assert n_checked >= 50, f"only {n_checked} blocked paths sampled, weak check"
    print(f"vectorized physics verified against scalar reference "
          f"(200 CNOSSOS rows, {n_checked} blocked paths)")


# --- geometry precompute (identical for all 16 runs) -------------------------

def load_canonical_segments():
    """The open-arm s42 parquet fixes the canonical segment order; every run is
    aligned onto it by (u, v, key). The closed arm drops exactly the closed
    edges, which align to zero flow, the correct physical reading."""
    df = pd.read_parquet(os.path.join(
        FWRQN_DIR, f"fwrqn_{ARMS[0]}_s{SEEDS[0]}_segments.parquet"))
    return df[["u", "v", "key"]].copy()


def discretize_sources(Gp, segs):
    """Point sources along each canonical segment's projected geometry.
    Returns (pt_xy float64 (n,2), pt_seg int32, pt_len float32, seg_len_m)."""
    xs, ys, seg_idx, sub_lens = [], [], [], []
    seg_len = np.full(len(segs), np.nan)
    missing = 0
    node_x = {n: d["x"] for n, d in Gp.nodes(data=True)}
    node_y = {n: d["y"] for n, d in Gp.nodes(data=True)}
    for i, (u, v, k) in enumerate(segs.itertuples(index=False)):
        try:
            d = Gp.edges[u, v, k]
        except KeyError:
            missing += 1
            continue
        length = float(d.get("length", 0.0) or 0.0)
        seg_len[i] = length
        if length <= 0:
            continue
        if "geometry" in d:
            coords = np.asarray(d["geometry"].coords)
        else:
            coords = np.array([[node_x[u], node_y[u]], [node_x[v], node_y[v]]])
        step = np.hypot(np.diff(coords[:, 0]), np.diff(coords[:, 1]))
        cum = np.concatenate([[0.0], np.cumsum(step)])
        geo_len = cum[-1]
        if geo_len <= 0:
            continue
        n_sub = max(1, int(np.ceil(geo_len / SRC_STEP_M)))
        # midpoints of equal sub-intervals; each carries length/n_sub metres of
        # the GRAPH length so total emitted power matches the per-metre model
        targets = (np.arange(n_sub) + 0.5) * geo_len / n_sub
        xs.append(np.interp(targets, cum, coords[:, 0]))
        ys.append(np.interp(targets, cum, coords[:, 1]))
        seg_idx.append(np.full(n_sub, i, dtype=np.int32))
        sub_lens.append(np.full(n_sub, length / n_sub, dtype=np.float32))
    if missing:
        print(f"WARNING: {missing} parquet segments not found in the graph")
    pt_xy = np.column_stack([np.concatenate(xs), np.concatenate(ys)])
    return (pt_xy, np.concatenate(seg_idx), np.concatenate(sub_lens), seg_len)


def build_pairs(pt_xy, pt_len, rec_xy, walls_xy, walls_h, walls_halflen):
    """Every (source point, receiver) pair within CUTOFF_M: spherical-spreading
    gain, plus band transmission for the pairs a wall blocks.

    Returns pair_rec, pair_pt (int32), pair_g (float32), blk_idx (int64 into
    the pair arrays), blk_T (float32 (k, 8))."""
    inv_cell = 1.0 / GRID_M
    cell = np.floor(pt_xy * inv_cell).astype(np.int64)
    order = np.lexsort((cell[:, 1], cell[:, 0]))
    cell_sorted = cell[order]
    keys, starts = np.unique(cell_sorted, axis=0, return_index=True)
    key_map = {tuple(kx): (s, e) for kx, s, e in
               zip(keys, starts, np.append(starts[1:], len(order)))}
    reach = int(np.ceil(CUTOFF_M * inv_cell))

    wall_mid = np.column_stack([(walls_xy[:, 0] + walls_xy[:, 2]) / 2.0,
                                (walls_xy[:, 1] + walls_xy[:, 3]) / 2.0])

    recs, pts, gains = [], [], []
    blk_pair_offsets, blk_T = [], []
    n_pairs = 0
    for r in range(len(rec_xy)):
        rx, ry = rec_xy[r]
        cx, cy = int(np.floor(rx * inv_cell)), int(np.floor(ry * inv_cell))
        idx_chunks = []
        for gx in range(cx - reach, cx + reach + 1):
            for gy in range(cy - reach, cy + reach + 1):
                se = key_map.get((gx, gy))
                if se:
                    idx_chunks.append(order[se[0]:se[1]])
        if not idx_chunks:
            continue
        cand = np.concatenate(idx_chunks)
        d = np.hypot(pt_xy[cand, 0] - rx, pt_xy[cand, 1] - ry)
        keep = d < CUTOFF_M
        cand, d = cand[keep], np.maximum(d[keep], MIN_DIST_M)
        if len(cand) == 0:
            continue
        g = (pt_len[cand] / (d * d)).astype(np.float32)

        # wall transmission for the paths a nearby wall crosses
        wsel = np.hypot(wall_mid[:, 0] - rx, wall_mid[:, 1] - ry) \
            < CUTOFF_M + walls_halflen + 50.0
        if wsel.any():
            best = best_delta_vec(pt_xy[cand], rx, ry,
                                  walls_xy[wsel], walls_h[wsel],
                                  bp.SOURCE_H_M, bp.RECEIVER_H_M)
            blocked = np.isfinite(best)
            if blocked.any():
                il = kurze_anderson_il_vec(best[blocked])
                real = il.max(axis=1) > 1e-6
                if real.any():
                    local = np.flatnonzero(blocked)[real]
                    blk_pair_offsets.append(n_pairs + local)
                    blk_T.append((10.0 ** (-il[real] / 10.0)).astype(np.float32))

        recs.append(np.full(len(cand), r, dtype=np.int32))
        pts.append(cand.astype(np.int32))
        gains.append(g)
        n_pairs += len(cand)

    pair_rec = np.concatenate(recs)
    pair_pt = np.concatenate(pts)
    pair_g = np.concatenate(gains)
    blk_idx = (np.concatenate(blk_pair_offsets) if blk_pair_offsets
               else np.empty(0, dtype=np.int64))
    T = (np.concatenate(blk_T) if blk_T else np.empty((0, 8), dtype=np.float32))
    return pair_rec, pair_pt, pair_g, blk_idx, T


# --- per-run energies --------------------------------------------------------

def run_band_energy(run_name, canon, seg_len, canon_pos):
    """Per-canonical-segment band energy per metre for one saved run."""
    df = pd.read_parquet(os.path.join(FWRQN_DIR, f"{run_name}_segments.parquet"))
    q = np.zeros(len(canon))
    val = np.zeros(len(canon))
    pos = np.array([canon_pos.get(t, -1)
                    for t in zip(df["u"], df["v"], df["key"])])
    if (pos < 0).any():
        raise SystemExit(f"{run_name}: {(pos < 0).sum()} segments not in the "
                         f"canonical open-arm set; arms cannot be paired")
    q[pos] = df["throughput"].to_numpy(dtype=float)
    val[pos] = df["value"].to_numpy(dtype=float)
    flowing = (q > 0) & (val > 0) & np.isfinite(seg_len) & (seg_len > 0)
    v_kph = np.zeros(len(canon))
    v_kph[flowing] = 3.6 * seg_len[flowing] * q[flowing] / val[flowing]
    capped = int((v_kph > V_CAP_KPH).sum())
    v_kph = np.minimum(v_kph, V_CAP_KPH)
    if capped:
        print(f"    ({capped} short-segment speeds capped at {V_CAP_KPH:.0f} "
              f"km/h, see V_CAP_KPH note)")
    return band_energy_per_m(np.where(flowing, q, 0.0), v_kph)


def receiver_energies(w, pair_rec, pair_seg, pair_g, blk_idx, blk_T,
                      blk_seg, n_rec):
    """(with-walls, barrier-blind) receiver energy vectors for one run."""
    w_tot = w.sum(axis=1)
    e = pair_g * w_tot[pair_seg]
    e_blind = np.bincount(pair_rec, weights=e, minlength=n_rec)
    e_wall_pairs = e.copy()
    e_wall_pairs[blk_idx] = pair_g[blk_idx] * np.einsum(
        "kb,kb->k", w[blk_seg], blk_T.astype(np.float64))
    e_wall = np.bincount(pair_rec, weights=e_wall_pairs, minlength=n_rec)
    return e_wall, e_blind


# --- main --------------------------------------------------------------------

def main(rebuild_pairs=False):
    rng = np.random.default_rng(42)

    walls = pd.read_parquet(WALLS_PARQUET)
    walls_xy = walls[["x0", "y0", "x1", "y1"]].to_numpy()
    walls_h = walls["ht_m"].to_numpy()
    walls_halflen = walls["len_m"].to_numpy() / 2.0
    verify_vectorized(walls_xy, walls_h, rng)

    canon = load_canonical_segments()
    canon_pos = {t: i for i, t in
                 enumerate(zip(canon["u"], canon["v"], canon["key"]))}

    bg = pd.read_parquet(RECEIVERS_PARQUET)
    from pyproj import Transformer
    fwd = Transformer.from_crs("EPSG:4326", walls["proj_crs"].iloc[0],
                               always_xy=True)
    rx, ry = fwd.transform(bg["lon"].to_numpy(), bg["lat"].to_numpy())
    rec_xy = np.column_stack([rx, ry])
    n_rec = len(bg)

    cache_ok = False
    if os.path.exists(PAIRS_CACHE) and not rebuild_pairs:
        z = np.load(PAIRS_CACHE)
        cache_ok = (float(z["cutoff_m"]) == CUTOFF_M
                    and float(z["step_m"]) == SRC_STEP_M
                    and int(z["n_walls"]) == len(walls)
                    and int(z["n_rec"]) == n_rec)
        if cache_ok:
            print(f"pair cache loaded from {PAIRS_CACHE}")
            pt_seg, seg_len = z["pt_seg"], z["seg_len"]
            pair_rec, pair_pt, pair_g = z["pair_rec"], z["pair_pt"], z["pair_g"]
            blk_idx, blk_T = z["blk_idx"], z["blk_T"]
    if not cache_ok:
        import osmnx as ox
        import hashlib
        with open(barriers.DEFAULT_GRAPH, "rb") as f:
            md5 = hashlib.md5(f.read()).hexdigest()
        if md5 != barriers.PREREG_GRAPH_MD5:
            print("WARNING: graph is not the prereg pin; runs may not align")
        else:
            print("graph md5 matches the prereg Appendix R pin")
        print("loading graph (93 MB, takes a minute)...")
        Gp = ox.project_graph(ox.load_graphml(barriers.DEFAULT_GRAPH))
        assert str(Gp.graph["crs"]) == str(walls["proj_crs"].iloc[0]), \
            "graph and wall projections differ"
        print("discretizing sources...")
        pt_xy, pt_seg, pt_len, seg_len = discretize_sources(Gp, canon)
        print(f"{len(pt_xy):,} point sources from {len(canon):,} segments")
        print("building source-receiver pairs (spatial hash + wall checks)...")
        pair_rec, pair_pt, pair_g, blk_idx, blk_T = build_pairs(
            pt_xy, pt_len, rec_xy, walls_xy, walls_h, walls_halflen)
        np.savez_compressed(
            PAIRS_CACHE, pt_seg=pt_seg, seg_len=seg_len, pair_rec=pair_rec,
            pair_pt=pair_pt, pair_g=pair_g, blk_idx=blk_idx, blk_T=blk_T,
            cutoff_m=CUTOFF_M, step_m=SRC_STEP_M, n_walls=len(walls),
            n_rec=n_rec)
        print(f"pair cache written to {PAIRS_CACHE}")

    pair_seg = pt_seg[pair_pt]
    blk_seg = pair_seg[blk_idx]
    blk_share = 100.0 * len(blk_idx) / max(len(pair_rec), 1)
    med_T = float(np.median(blk_T.sum(axis=1) / 8.0)) if len(blk_T) else 1.0
    print(f"{len(pair_rec):,} pairs, {len(blk_idx):,} wall-blocked "
          f"({blk_share:.1f}%), median blocked band transmission {med_T:.2f}")

    # 16 runs -> 4 energy panels per receiver per seed
    E = {(arm, kind): np.zeros((len(SEEDS), n_rec))
         for arm in ARMS for kind in ("wall", "blind")}
    for arm in ARMS:
        for si, seed in enumerate(SEEDS):
            w = run_band_energy(f"fwrqn_{arm}_s{seed}", canon, seg_len,
                                canon_pos)
            e_wall, e_blind = receiver_energies(
                w, pair_rec, pair_seg, pair_g, blk_idx, blk_T, blk_seg, n_rec)
            E[(arm, "wall")][si] = e_wall
            E[(arm, "blind")][si] = e_blind
            print(f"  fwrqn_{arm}_s{seed}: network per-m source energy "
                  f"{w.sum():.3e}")

    # paired per-seed deltas, energy domain, then medians across seeds
    with np.errstate(divide="ignore", invalid="ignore"):
        d_wall = 10.0 * np.log10(E[("rosequarter", "wall")]
                                 / E[("open", "wall")])
        d_blind = 10.0 * np.log10(E[("rosequarter", "blind")]
                                  / E[("open", "blind")])
        shield = 10.0 * np.log10(E[("open", "blind")] / E[("open", "wall")])
    valid = np.isfinite(d_wall) & np.isfinite(d_blind) & np.isfinite(shield)
    n_valid = valid.sum(axis=0)
    ok = n_valid >= MIN_VALID_SEEDS

    def med(a):
        m = np.where(valid, a, np.nan)
        with np.errstate(all="ignore"):
            return np.where(ok, np.nanmedian(m, axis=0), np.nan)

    out = bg.copy()
    out["x"], out["y"] = rec_xy[:, 0], rec_xy[:, 1]
    out["n_valid_seeds"] = n_valid
    out["d_wall_db"] = med(d_wall)
    out["d_blind_db"] = med(d_blind)
    out["wedge_db"] = med(d_wall - d_blind)
    out["shield_db"] = med(shield)
    out["n_seeds_up"] = np.where(valid, d_wall > 0, False).sum(axis=0)
    os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
    out.to_parquet(OUT_PARQUET, index=False)
    print(f"\nwrote {OUT_PARQUET}")

    report(out)
    make_figure(out, walls)


def report(out):
    ok = out["d_wall_db"].notna()
    d = out[ok]
    pop = d["population"].to_numpy(dtype=float)
    print(f"\n{ok.sum()} of {len(out)} receivers valid on >= "
          f"{MIN_VALID_SEEDS} paired seeds "
          f"(population covered {pop.sum():,.0f})")
    print(f"closure noise change at centroids, median across seeds: "
          f"median {d['d_wall_db'].median():+.2f} dB, "
          f"IQR {d['d_wall_db'].quantile(0.25):+.2f} to "
          f"{d['d_wall_db'].quantile(0.75):+.2f}")

    unanimous = d["n_seeds_up"].isin([0, len(SEEDS)])
    for thr in (0.5, 1.0):
        up = d["d_wall_db"] >= thr
        dn = d["d_wall_db"] <= -thr
        print(f"  |change| >= {thr} dB: {pop[up].sum():,.0f} residents up "
              f"({pop[up & unanimous].sum():,.0f} unanimous across seeds), "
              f"{pop[dn].sum():,.0f} down "
              f"({pop[dn & unanimous].sum():,.0f} unanimous)")

    shielded = d["shield_db"] >= 1.0
    print(f"\nwall-shielded receivers (>= 1 dB current shielding): "
          f"{shielded.sum()} ({pop[shielded].sum():,.0f} residents)")
    for name, m in (("shielded", shielded), ("unshielded", ~shielded)):
        print(f"  {name}: closure change median "
              f"{d.loc[m, 'd_wall_db'].median():+.2f} dB "
              f"(blind model says {d.loc[m, 'd_blind_db'].median():+.2f}), "
              f"wedge median {d.loc[m, 'wedge_db'].median():+.2f} dB")

    big = d.reindex(d["d_wall_db"].abs().sort_values(ascending=False).index)
    print("\nlargest closure changes (block group, pop, change, blind, "
          "wedge, shielding, seeds up/8):")
    for _, r in big.head(10).iterrows():
        print(f"  {r['bg_geoid']}  pop {r['population']:>5.0f}  "
              f"{r['d_wall_db']:+.2f} dB (blind {r['d_blind_db']:+.2f}, "
              f"wedge {r['wedge_db']:+.2f}, shield {r['shield_db']:.2f})  "
              f"{int(r['n_seeds_up'])}/8")


def make_figure(out, walls):
    d = out[out["d_wall_db"].notna()]
    lim = max(1.0, float(d["d_wall_db"].abs().quantile(0.99)))
    fig, axes = plt.subplots(1, 3, figsize=(19, 6.5))

    ax = axes[0]
    sc = ax.scatter(d["lon"], d["lat"], c=d["d_wall_db"], cmap="RdBu_r",
                    vmin=-lim, vmax=lim, s=14, linewidths=0)
    ax.plot([walls["lon0"], walls["lon1"]], [walls["lat0"], walls["lat1"]],
            color="k", lw=1.0)
    fig.colorbar(sc, ax=ax, label="closure noise change, dB (median of 8 seeds)")
    ax.set_title("Barrier-aware closure change at block-group centroids")
    ax.set_aspect(1.0 / np.cos(np.radians(45.5)))

    ax = axes[1]
    z = d[(d["lon"] > ZOOM[0]) & (d["lon"] < ZOOM[1])
          & (d["lat"] > ZOOM[2]) & (d["lat"] < ZOOM[3])]
    sc = ax.scatter(z["lon"], z["lat"], c=z["d_wall_db"], cmap="RdBu_r",
                    vmin=-lim, vmax=lim, s=90, linewidths=0.4,
                    edgecolors="k")
    ax.plot([walls["lon0"], walls["lon1"]], [walls["lat0"], walls["lat1"]],
            color="k", lw=2.0)
    ax.set_xlim(ZOOM[0], ZOOM[1])
    ax.set_ylim(ZOOM[2], ZOOM[3])
    ax.ticklabel_format(useOffset=False)
    fig.colorbar(sc, ax=ax, label="closure noise change, dB")
    ax.set_title("Rose Quarter zoom (black = ODOT walls)")
    ax.set_aspect(1.0 / np.cos(np.radians(45.53)))

    ax = axes[2]
    sc = ax.scatter(d["shield_db"], d["wedge_db"], c=d["d_wall_db"],
                    cmap="RdBu_r", vmin=-lim, vmax=lim, s=14, linewidths=0)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("current wall shielding at the receiver (dB)")
    ax.set_ylabel("barrier wedge: with-walls change minus blind change (dB)")
    fig.colorbar(sc, ax=ax, label="closure change, dB")
    ax.set_title("The walls' fingerprint on the closure")

    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT_FIG), exist_ok=True)
    fig.savefig(OUT_FIG, dpi=150)
    print(f"wrote {OUT_FIG}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-pairs", action="store_true",
                    help="ignore the cached geometry and rebuild it")
    args = ap.parse_args()
    main(rebuild_pairs=args.rebuild_pairs)
