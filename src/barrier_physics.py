"""
Single-barrier diffraction physics: Maekawa via the Kurze-Anderson formula.

The picture: sound leaving a road has to climb over a wall to reach a receiver
behind it. The climb makes the path longer than the straight line, and the
extra length (the path-length difference, delta) is what a thin-screen barrier
attenuates by. Kurze-Anderson turns delta into an insertion loss per frequency:
higher frequencies (shorter wavelengths) are blocked more, which is why traffic
behind a wall sounds muffled, not just quieter.

Formula (Kurze & Anderson 1971, the standard fit to Maekawa's chart), with the
Fresnel number N = 2 * delta * f / c:

    N >  0        IL = 5 + 20*log10( sqrt(2*pi*N) / tanh(sqrt(2*pi*N)) )
    -0.2 < N <= 0 IL = 5 + 20*log10( sqrt(2*pi*|N|) / tan(sqrt(2*pi*|N|)) )
    N <= -0.2     IL = 0

The middle branch is the transition just above the line of sight (the wall top
grazes the path); delta is SIGNED, negative when the wall does not break the
line of sight. IL is capped at 20 dB, the FHWA TNM cap for walls, because
measured walls never deliver the uncapped 25+ dB the formula can produce
(flanking, scattering, and multiple reflections leak sound around).

v1 simplifications, stated plainly: single diffraction over the top only (no
double-diffraction for berms with walls, no diffraction around the wall ENDS;
a path that misses the wall in plan view gets zero IL, which is what makes
finite wall length matter). Flat terrain: road, wall base, and receiver ground
all on one plane. Thin screen: the wall has height but no thickness.

Pure functions, no I/O. Self-test: python src/barrier_physics.py
"""

import os
import sys

import numpy as np

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from noise import OCTAVE_BANDS_HZ, A_WEIGHTING_DB, per_vehicle_band_power

C_SOUND_MS = 343.0    # speed of sound, m/s, at ~20 C
IL_CAP_DB = 20.0      # TNM's cap for walls; the formula alone overshoots reality
SOURCE_H_M = 0.05     # CNOSSOS-EU equivalent road source height
RECEIVER_H_M = 1.5    # standard ear-height receiver


def kurze_anderson_il(delta_m, freqs_hz=OCTAVE_BANDS_HZ):
    """Insertion loss (dB) per frequency for a signed path-length difference.

    delta_m > 0 means the wall top breaks the source-receiver line of sight.
    Returns an array aligned to freqs_hz, each value in [0, IL_CAP_DB]."""
    n = 2.0 * delta_m * np.asarray(freqs_hz, dtype=float) / C_SOUND_MS
    il = np.zeros_like(n)
    pos = n > 1e-9
    x = np.sqrt(2.0 * np.pi * n[pos])
    il[pos] = 5.0 + 20.0 * np.log10(x / np.tanh(x))
    trans = (n <= 1e-9) & (n > -0.2)
    x = np.sqrt(2.0 * np.pi * np.abs(n[trans]))
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(x > 1e-9, x / np.tan(x), 1.0)   # x/tan(x) -> 1 as x -> 0
    il[trans] = np.maximum(5.0 + 20.0 * np.log10(v), 0.0)
    return np.clip(il, 0.0, IL_CAP_DB)


def crossing_point(sx, sy, rx, ry, wx0, wy0, wx1, wy1):
    """Plan-view intersection of segment source->receiver with a wall segment.

    Returns (ix, iy) or None. A path that clears the wall's END gets None,
    which is exactly the finite-length behavior we want (no end diffraction)."""
    dx, dy = rx - sx, ry - sy
    ex, ey = wx1 - wx0, wy1 - wy0
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None                     # parallel, no single crossing
    t = ((wx0 - sx) * ey - (wy0 - sy) * ex) / denom   # along source->receiver
    u = ((wx0 - sx) * dy - (wy0 - sy) * dx) / denom   # along the wall
    if 0.0 < t < 1.0 and 0.0 <= u <= 1.0:
        return sx + t * dx, sy + t * dy
    return None


def path_delta(sx, sy, sh, rx, ry, rh, ix, iy, wall_h):
    """Signed path-length difference over a wall top at (ix, iy, wall_h).

    Positive when the wall top is above the straight source-receiver sight
    line at the crossing, negative when the path clears the top."""
    d1 = float(np.hypot(ix - sx, iy - sy))            # source to wall, plan
    d2 = float(np.hypot(rx - ix, ry - iy))            # wall to receiver, plan
    dsr = d1 + d2                                     # total plan distance
    a = np.hypot(d1, wall_h - sh)                     # up over the top
    b = np.hypot(d2, wall_h - rh)                     # down the far side
    d = np.hypot(dsr, rh - sh)                        # the straight path
    delta = float(a + b - d)
    # height of the sight line where it passes the wall
    los_h = sh + (rh - sh) * (d1 / dsr) if dsr > 0 else sh
    return delta if wall_h >= los_h else -delta


def barrier_band_il(sx, sy, rx, ry, walls_xy, walls_h,
                    sh=SOURCE_H_M, rh=RECEIVER_H_M):
    """Octave-band insertion loss for one source-receiver path through a set of
    walls. walls_xy is an (n, 4) array of [x0, y0, x1, y1]; walls_h length n.

    With several walls in the way, the single most effective one (largest
    delta) is used; stacking Maekawa losses across multiple screens is known
    to overpredict, so v1 does not."""
    best_delta = None
    for (wx0, wy0, wx1, wy1), wh in zip(walls_xy, walls_h):
        hit = crossing_point(sx, sy, rx, ry, wx0, wy0, wx1, wy1)
        if hit is None:
            continue
        delta = path_delta(sx, sy, sh, rx, ry, rh, hit[0], hit[1], wh)
        if best_delta is None or delta > best_delta:
            best_delta = delta
    if best_delta is None:
        return np.zeros(len(OCTAVE_BANDS_HZ))
    return kurze_anderson_il(best_delta)


def broadband_il_dba(band_il, v_kph):
    """Collapse a band IL vector to one A-weighted dB(A) reduction, weighted by
    the CNOSSOS category-1 traffic spectrum at speed v_kph.

    The weighting matters: a wall blocks 2 kHz far better than 63 Hz, so the
    broadband number depends on where the traffic's energy sits. Propagation
    terms cancel (same path with and without the wall), so only the source
    spectrum is needed."""
    spec = per_vehicle_band_power(v_kph) + A_WEIGHTING_DB
    w = 10.0 ** (spec / 10.0)
    w /= w.sum()
    return -10.0 * np.log10(np.sum(w * 10.0 ** (-np.asarray(band_il) / 10.0)))


def _selftest():
    """Hand-checkable values, the scenarios.py discipline applied to physics."""
    ok = True

    # Kurze-Anderson at N=0 is exactly 5 dB (the grazing-incidence value)
    il0 = kurze_anderson_il(0.0, np.array([1000.0]))[0]
    ok &= abs(il0 - 5.0) < 0.05
    print(f"N=0 grazing: {il0:.2f} dB (want 5.00)")

    # N=1 sits near 13 dB on Maekawa's chart
    delta_n1 = C_SOUND_MS / (2.0 * 1000.0)            # delta making N=1 at 1 kHz
    il1 = kurze_anderson_il(delta_n1, np.array([1000.0]))[0]
    ok &= abs(il1 - 13.1) < 0.3
    print(f"N=1: {il1:.2f} dB (Maekawa chart ~13)")

    # deep shadow hits the 20 dB cap
    il10 = kurze_anderson_il(10 * delta_n1, np.array([1000.0]))[0]
    ok &= il10 == IL_CAP_DB
    print(f"N=10: {il10:.2f} dB (capped at {IL_CAP_DB})")

    # a worked geometry: source at origin, 3 m wall at x=10, receiver at x=25.
    # By hand: a=sqrt(100+2.95^2)=10.4260, b=sqrt(225+1.5^2)=15.0748,
    # d=sqrt(625+1.45^2)=25.0420, delta=0.4588 m.
    hit = crossing_point(0, 0, 25, 0, 10, -50, 10, 50)
    delta = path_delta(0, 0, SOURCE_H_M, 25, 0, RECEIVER_H_M, hit[0], hit[1], 3.0)
    ok &= abs(delta - 0.4588) < 0.001
    print(f"worked geometry delta: {delta:.4f} m (hand value 0.4588)")

    # the same path past the END of the wall must miss it entirely
    ok &= crossing_point(0, 60, 25, 60, 10, -50, 10, 50) is None
    print("path beyond the wall end: no crossing (finite length respected)")

    # a wall top below the sight line gives a negative delta and near-zero IL
    d_low = path_delta(0, 0, 4.0, 25, 0, 4.0, hit[0], hit[1], 1.0)
    ok &= d_low < 0
    il_low = kurze_anderson_il(d_low, np.array([63.0]))[0]
    print(f"wall below sight line: delta={d_low:.4f} m, IL(63 Hz)={il_low:.2f} dB")

    # broadband collapse: uniform 10 dB in every band must give exactly 10 dB(A)
    bb = broadband_il_dba(np.full(8, 10.0), 100.0)
    ok &= abs(bb - 10.0) < 1e-9
    print(f"uniform-band collapse: {bb:.2f} dB(A) (want 10.00)")

    # and the full chain on the worked geometry, freeway spectrum
    band = barrier_band_il(0, 0, 25, 0, np.array([[10, -50, 10, 50]]), [3.0])
    bb = broadband_il_dba(band, 100.0)
    print(f"worked geometry broadband: {bb:.1f} dB(A) "
          f"(bands 63 Hz {band[0]:.1f} to 8 kHz {band[-1]:.1f})")
    ok &= band[0] < band[-1]                          # high bands blocked more

    print("SELF-TEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
