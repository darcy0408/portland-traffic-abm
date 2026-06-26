"""ROAD-TRAFFIC NOISE surface (CNOSSOS-EU), the project's second output surface.

This is the first version of the "week 8" noise path. The ABM already turns
vehicle interactions into an NO2 surface; this module turns the SAME run into a
per-segment road-traffic noise surface, in dB(A), using the European CNOSSOS-EU
road source method. It runs no simulation: it reads one saved run's per-segment
results and the cached graph, and writes a new noise parquet. The eventual
comparison is model-to-model against the FHWA Traffic Noise Model (TNM); that
comparison is NOT implemented here, only the ABM-side mechanistic surface.

Why CNOSSOS fits this project: noise, like the NO2 path, is produced from the
agents' realized behavior. A queued, crawling car and a free-flowing car at the
same location emit different sound power, and CNOSSOS makes sound power an
explicit function of speed and flow. So the congestion the ABM produces feeds
straight into the noise surface, which is the whole reason to use an agent model.

-----------------------------------------------------------------------------
SOURCE MODEL (what is implemented)
-----------------------------------------------------------------------------
Reference: Commission Directive (EU) 2015/996 of 19 May 2015 establishing common
noise assessment methods (CNOSSOS-EU), Annex II, road traffic noise; and the JRC
reference report "Common Noise Assessment Methods in Europe (CNOSSOS-EU)",
Kephalopoulos, Paviotti and Anfosso-Ledee, EUR 25379 EN, 2012.

For one vehicle of category m traveling at speed v (km/h), the sound power in
each octave band i is the energy sum of a rolling-noise term and a
propulsion-noise term:

  rolling:      L_WR,i,m  = A_R,i,m + B_R,i,m * log10(v / v_ref)
  propulsion:   L_WP,i,m  = A_P,i,m + B_P,i,m * (v - v_ref) / v_ref
  per vehicle:  L_W,i,m   = 10 * log10( 10^(L_WR/10) + 10^(L_WP/10) )

with v_ref = 70 km/h. Rolling noise dominates at higher speed (the log term grows
with v), propulsion noise dominates at low speed and under acceleration. We
implement ONLY category 1 (light motor vehicles, i.e. passenger cars). That
matches the rest of this project, which already uses a single passenger-car class
for emissions (PC_D_EU4). Heavy vehicles (CNOSSOS categories 2 and 3, with much
higher sound power) are deliberately left as future work and are noted as a known
limitation: a real arterial's noise is raised by trucks and buses we do not model.

The per-vehicle band powers are combined with the traffic flow into a line-source
sound power per metre of road. For a flow of Q vehicles per hour at mean speed v
(km/h), the equivalent sound power per metre in band i is:

  L_W',i  = L_W,i  + 10 * log10( Q / (1000 * v) )

The Q / (1000 * v) factor is the mean number of vehicles present per metre of road
at any instant (Q per hour divided by speed gives vehicles per km, divided by 1000
gives vehicles per metre). More cars, or slower cars (more time spent on the
segment), means more simultaneous sources per metre and a louder line.

A single A-weighted number is then formed by energy-summing the eight octave bands
(63 Hz to 8 kHz) after adding the standard A-weighting correction per band:

  L_WA' = 10 * log10( sum_i 10^( (L_W',i + A_i) / 10 ) )      [dB(A) per metre]

-----------------------------------------------------------------------------
PROPAGATION (deliberately simple, clearly a first pass)
-----------------------------------------------------------------------------
We place one representative receiver at a fixed distance from each segment and
apply ONLY geometric divergence for an infinite incoherent line source. Treating a
segment as an infinitely long line (valid when the receiver distance is small
relative to the segment length), the sound pressure level at distance d is:

  L_p(d) = L_WA' - 10 * log10(d) - 10 * log10(2*pi)
         = L_WA' - 10 * log10(d) - 7.98   dB(A)

The -10*log10(d) is cylindrical spreading (a line source loses 3 dB per distance
doubling, unlike a point source's 6 dB), and the -7.98 dB is the 1/(2*pi*d)
constant of a full free-field cylinder. We report the level at RECEIVER_DIST_M
(10 m), a near-roadside receiver, and label it an Leq-style level for the
simulated hour.

Terms we DROP in this first version, every one a real effect we are not modeling:
  - ground effect (A_ground): absorption/reflection over soft vs hard ground,
  - atmospheric absorption (A_atm): air absorption, frequency dependent,
  - barriers and diffraction (A_bar): walls, buildings, terrain screening,
  - meteorological correction: wind and temperature gradients (favorable/neutral),
  - facade and multiple reflections, and source/segment directivity,
  - finite segment length and road geometry (we assume an infinite straight line),
  - heavy-vehicle categories (cars only), and a real road-surface correction.
These are exactly where the FHWA TNM reference comparison would later plug in:
TNM does ground, barriers, and a finite-geometry integration this v1 does not.

-----------------------------------------------------------------------------
SPEED RECOVERY (how the surface becomes congestion-aware)
-----------------------------------------------------------------------------
The saved run stores no per-segment speed, but it stores 'value' = total
vehicle-seconds of activity on the segment and 'throughput' = vehicles that fully
crossed it in the hour. A vehicle on a segment of length L (m) at speed s spends
L/s seconds there, so summed over vehicles the total time is 'value' and the mean
time per vehicle is value/throughput. The realized mean speed is therefore:

  v_mean = L * throughput / value     (m/s)

This is the congestion-aware speed: on a jammed Powell segment it drops to a few
m/s, which both raises the per-metre source power (cars linger) and lowers the
rolling-noise term, the physical trade-off CNOSSOS captures. Segments with zero
throughput or zero activity carry no flow and emit no noise (silent).
"""
import os
import sys

import numpy as np
import pandas as pd
import osmnx as ox

# make sibling modules importable whether run from repo root or from src/
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


# --- CNOSSOS-EU category 1 (light vehicles) coefficients --------------------
# Octave-band centre frequencies (Hz), 63 to 8000. All coefficient arrays below
# are aligned to this order. Source: Directive (EU) 2015/996, Annex II, road
# source coefficient tables for vehicle category 1 (and the CNOSSOS-EU JRC
# reference report EUR 25379 EN, 2012).
OCTAVE_BANDS_HZ = np.array([63, 125, 250, 500, 1000, 2000, 4000, 8000])

# Rolling-noise coefficients: A_R is the band sound power at the reference speed,
# B_R is the slope against log10(v/v_ref).
AR_CAT1 = np.array([79.7, 85.7, 84.5, 90.2, 97.3, 93.9, 84.1, 74.3])
BR_CAT1 = np.array([30.0, 41.5, 38.9, 25.7, 32.5, 37.2, 39.0, 40.0])

# Propulsion-noise coefficients: A_P is the band sound power at the reference
# speed, B_P is the slope against the linear (v - v_ref)/v_ref term.
AP_CAT1 = np.array([94.5, 89.2, 88.0, 85.9, 84.2, 86.9, 83.3, 76.1])
BP_CAT1 = np.array([-1.3, 7.2, 7.7, 8.0, 8.0, 8.0, 8.0, 8.0])

# Reference speed for the CNOSSOS road source coefficients.
V_REF_KPH = 70.0

# Standard A-weighting correction (dB) at each octave-band centre frequency. Added
# per band before the energy sum so the single output number is A-weighted, dB(A).
A_WEIGHTING_DB = np.array([-26.2, -16.1, -8.6, -3.2, 0.0, 1.2, 1.0, -1.1])

# CNOSSOS coefficients are validated for roughly 20 to 130 km/h for category 1.
# Below 20 km/h the formula is not defined and would make crawling/idling traffic
# unrealistically quiet (the rolling term keeps dropping with log10(v)). We floor
# the speed fed to the source formula at 20 km/h, a standard CNOSSOS application
# rule. The vehicle-presence term Q/(1000*v) still uses the TRUE low speed, so a
# jam correctly piles up more simultaneous sources per metre.
V_FLOOR_KPH = 20.0

# Receiver distance (m) for the propagation step: a near-roadside receiver. The
# reported per-segment level is the sound pressure level here.
RECEIVER_DIST_M = 10.0


def per_vehicle_band_power(v_kph):
    """Per-vehicle octave-band sound power L_W,i (dB) for category 1 at speed
    v_kph (km/h). Returns an 8-vector aligned to OCTAVE_BANDS_HZ.

    Energy sum of the rolling and propulsion terms, band by band. The speed used
    in the formula is floored at V_FLOOR_KPH (see note above)."""
    v = max(float(v_kph), V_FLOOR_KPH)
    lwr = AR_CAT1 + BR_CAT1 * np.log10(v / V_REF_KPH)          # rolling noise
    lwp = AP_CAT1 + BP_CAT1 * (v - V_REF_KPH) / V_REF_KPH       # propulsion noise
    return 10.0 * np.log10(10.0 ** (lwr / 10.0) + 10.0 ** (lwp / 10.0))


def segment_line_power_dba(q_vph, v_kph):
    """A-weighted line-source sound power per metre, L_WA' in dB(A), for a flow of
    q_vph vehicles/hour at mean speed v_kph (km/h).

    Combines the per-vehicle band powers with the flow term 10*log10(Q/(1000*v))
    and energy-sums the A-weighted octave bands into one number. v_kph here is the
    TRUE mean speed (not floored) for the flow term, while the per-vehicle source
    uses the floored speed inside per_vehicle_band_power."""
    if q_vph <= 0 or v_kph <= 0:
        return None                                   # no flow, no source
    lw_band = per_vehicle_band_power(v_kph)
    # vehicles present per metre at any instant: Q per hour / speed -> per km / 1000
    flow_term = 10.0 * np.log10(q_vph / (1000.0 * v_kph))
    lw_line_band = lw_band + flow_term
    # energy-sum the A-weighted bands into a single dB(A) per metre
    return 10.0 * np.log10(np.sum(10.0 ** ((lw_line_band + A_WEIGHTING_DB) / 10.0)))


def propagate_line(lwa_per_m, dist_m=RECEIVER_DIST_M):
    """Sound pressure level (dB(A)) at dist_m from an infinite incoherent line
    source of A-weighted power per metre lwa_per_m. Geometric divergence only:
    L_p = L_W' - 10*log10(d) - 10*log10(2*pi). See the module docstring for the
    long list of propagation terms this drops."""
    return lwa_per_m - 10.0 * np.log10(dist_m) - 10.0 * np.log10(2.0 * np.pi)


def load_run_segments(run_name=None):
    """Load one ABM run's per-segment results (u, v, key, value, throughput, ...)."""
    run_name = config.RUN_NAME if run_name is None else run_name
    path = os.path.join(config.PROCESSED_DIR, f"{run_name}_segments.parquet")
    if not os.path.exists(path):
        raise SystemExit(f"No results at {path}; the run must already be on disk "
                         f"(this script never runs the simulation).")
    return pd.read_parquet(path)


def load_network():
    """Load the cached OSMnx graph (segment length and street name live here)."""
    return ox.load_graphml(os.path.join(config.NETWORK_DIR, "graph.graphml"))


def _edge_length_and_name(G):
    """Per-edge length (m) and street name, keyed by (u, v, key). The parquet has
    no geometry, so length comes from the graph; name is only for sanity reports."""
    length, name = {}, {}
    for u, v, k, d in G.edges(keys=True, data=True):
        length[(u, v, k)] = float(d.get("length", 10.0) or 10.0)
        nm = d.get("name")
        if isinstance(nm, list):
            nm = nm[0]
        name[(u, v, k)] = nm
    return length, name


def build_noise_surface(run_name=None, dist_m=RECEIVER_DIST_M):
    """Build the per-segment CNOSSOS noise surface for one saved run.

    Recovers a congestion-aware mean speed per segment (v_mean = L*throughput/value),
    treats throughput as the hourly flow Q, and computes the CNOSSOS line-source
    level propagated to a near receiver. Returns a DataFrame with columns:
        u, v, key            segment identity (matches the parquet / graph edges)
        length_m             segment length from the graph
        q_vph                flow in vehicles/hour (= throughput)
        v_mean_mps           realized mean speed (m/s), NaN where there is no flow
        noise_db             dB(A) at dist_m, NaN where there is no flow
    Segments with no throughput or no activity get noise_db = NaN (silent street).
    """
    df = load_run_segments(run_name).copy()
    G = load_network()
    length, _name = _edge_length_and_name(G)

    df["length_m"] = [length.get((r.u, r.v, r.key), np.nan) for r in df.itertuples()]
    df["q_vph"] = df["throughput"].astype(float)        # throughput = veh/hour directly

    # congestion-aware realized mean speed; guard the divide-by-zero (no flow ->
    # no speed -> no noise). value is vehicle-seconds, throughput is vehicle count.
    flowing = (df["throughput"] > 0) & (df["value"] > 0)
    v_mean = np.full(len(df), np.nan)
    v_mean[flowing.to_numpy()] = (
        df.loc[flowing, "length_m"] * df.loc[flowing, "throughput"]
        / df.loc[flowing, "value"]
    ).to_numpy()
    df["v_mean_mps"] = v_mean

    # per-segment dB(A): CNOSSOS line-source power then geometric divergence
    noise = np.full(len(df), np.nan)
    for i, r in enumerate(df.itertuples()):
        if not (r.q_vph > 0 and np.isfinite(r.v_mean_mps) and r.v_mean_mps > 0):
            continue
        lwa_per_m = segment_line_power_dba(r.q_vph, r.v_mean_mps * 3.6)  # m/s -> km/h
        if lwa_per_m is None:
            continue
        noise[i] = propagate_line(lwa_per_m, dist_m)
    df["noise_db"] = noise

    return df[["u", "v", "key", "length_m", "q_vph", "v_mean_mps", "noise_db"]]


def main():
    """Build and save the noise surface for config.RUN_NAME, with sanity numbers.

    Reads the existing run parquet, writes data/processed/<run>_noise.parquet, and
    prints min/median/max dB(A) plus how many segments carry flow. Run with:
        python src/noise.py            # uses config.RUN_NAME
        python src/noise.py <run_name> # any saved run, e.g. powell_no2_open
    """
    run = sys.argv[1] if len(sys.argv) > 1 else config.RUN_NAME
    surf = build_noise_surface(run)

    out = os.path.join(config.PROCESSED_DIR, f"{run}_noise.parquet")
    surf.to_parquet(out, index=False)

    lit = surf["noise_db"].dropna()
    n_flow = int(len(lit))
    n_total = int(len(surf))
    print(f"Built CNOSSOS noise surface for '{run}': {n_total} segments, "
          f"{n_flow} carry flow ({n_total - n_flow} silent).")
    if n_flow:
        print(f"  dB(A) at {RECEIVER_DIST_M:.0f} m receiver: "
              f"min {lit.min():.1f}, median {lit.median():.1f}, max {lit.max():.1f}")
    print(f"Saved to {out}")
    print("Draw it with: python src/visualize_noise.py "
          + ("" if run == config.RUN_NAME else run))


if __name__ == "__main__":
    main()
