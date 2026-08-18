"""Model freeway speeds vs PORTAL loop detectors: is the jamming real?

The queue diagnostic showed the model's bottleneck MAP matches Portland's real
one (Banfield, Sunset, I-205, McLoughlin), but a few freeway mainline segments
run at 3-7 km/h with 90%+ stuck time, which looks harsher than reality. This
script measures that gap instead of eyeballing it.

Read-only: no simulation. Two sides are joined:

  REAL   PORTAL hourly per-detector volume+speed for baseline weekdays,
         aggregated to stations (volume-weighted speed across a station's
         lane detectors). Stations come from the PORTAL metadata API;
         mainline "2DS" stations only, the same exclusion rule the Rose
         Quarter pre-registration froze (ramp-meter stations have unreliable
         lane semantics).

  MODEL  Realized mean speed per edge from the finished lane-capacity sweep
         at the cited 16,500 demand (8 seeds, corrected lanes):
         v = v_sum / value, the same recovery the noise model uses.

Each station is snapped to the nearest same-ref mainline edge, direction
checked by bearing. The model hour is an AVERAGE-demand hour (16,500 is the
AADT-derived average), so the primary comparison is the real DAYTIME MEAN
(9:00-17:00); AM and PM peaks are shown to bracket.

Baseline days: three normal pre-closure weekdays, Tue-Thu Aug 11-13 2026,
matching the pre-registration's baseline rule (pre-Sept-11, not Labor Day
week). API responses are cached under data/portal/ so reruns are offline.

Usage:  python src/portal_speed_check.py
"""
import json
import math
import os
import sys
import urllib.request

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import osmnx as ox

import config

API = "https://new.portal.its.pdx.edu/highways/api"
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "portal")
GRAPH = os.path.join(config.NETWORK_DIR, "graph_metro20k_lanes.graphml")
DAYS = ["2026-08-11", "2026-08-12", "2026-08-13"]   # Tue-Thu, pre-closure
SEEDS = [42, 7, 13, 99, 2024, 314, 777, 8]
ARM = "lcap_realism_reallanes_n16500"

# PORTAL highway names -> the OSM ref used on the graph's mainline edges.
REF_MAP = [("I-5", "I 5"), ("I-84", "I 84"), ("I-205", "I 205"),
           ("I-405", "I 405"), ("26", "US 26"), ("217", "OR 217")]
# compass unit vector per PORTAL direction, for the direction check
DIR_VEC = {"NORTH": (0, 1), "SOUTH": (0, -1), "EAST": (1, 0), "WEST": (-1, 0)}

# The Rose Quarter pre-registration's frozen station set, flagged in the output.
FROZEN = {3121, 10642, 3172, 10640, 3120, 3185, 3122, 3196, 3110,
          10579, 3107, 10582, 3105}

MAX_SNAP_M = 250.0


def fetch(name, url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if not os.path.exists(path):
        print(f"  fetching {url}")
        with urllib.request.urlopen(url, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path) as f:
        return json.load(f)


def merc_to_lonlat(x, y):
    lon = x * 180.0 / 20037508.34
    lat = math.degrees(2 * math.atan(math.exp(y * math.pi / 20037508.34))
                       - math.pi / 2)
    return lon, lat


def is_active(props):
    return '"upper": null' in (props.get("active_dates") or "")


def osm_ref(hwy_name):
    for pat, ref in REF_MAP:
        if pat in hwy_name:
            return ref
    return None


def build():
    """Everything main() needs, importable: run the station-to-edge comparison
    and return its pieces so other read-only diagnostics (blackspot_trace) can
    start from the same matched stations instead of re-deriving the join.

    Returns (res, seg, G, n_seeds): res is one row per matched station with the
    snapped edge key kept in "edge"; seg is the seed-summed per-edge stats keyed
    by (u, v, key); G is the loaded lanes graph.
    """
    # --- PORTAL metadata ---------------------------------------------------
    hmeta = fetch("hwymeta.json", f"{API}/highwaymetadata/?format=json")
    if isinstance(hmeta, dict):
        hmeta = hmeta.get("features", hmeta)
    hprops = [h.get("properties", h) for h in hmeta]
    hwys = {h["highwayid"]: h for h in hprops}

    smeta = fetch("stationmeta.json", f"{API}/stationmetadata/?format=json")
    stations = {}
    for feat in smeta["features"]:
        if not feat.get("geometry"):
            continue                       # a few stations carry no location
        p, (x, y) = feat["properties"], feat["geometry"]["coordinates"]
        hwy = hwys.get(p["highwayid"])
        if hwy is None or not is_active(p):
            continue
        if "2DS" not in (p.get("locationtext") or ""):
            continue                       # mainline dual-loop stations only
        ref = osm_ref(hwy["highwayname"])
        if ref is None or hwy["direction"] not in DIR_VEC:
            continue
        lon, lat = merc_to_lonlat(x, y)
        stations[p["stationid"]] = {
            "lon": lon, "lat": lat, "ref": ref,
            "dir": hwy["direction"], "text": p["locationtext"]}
    print(f"active mainline 2DS stations on mapped highways: {len(stations)}")

    dmeta = fetch("detmeta.json", f"{API}/detectormetadata/?format=json")
    if isinstance(dmeta, dict):
        dmeta = dmeta.get("features", dmeta)
    dprops = [d.get("properties", d) for d in dmeta]
    det2sta = {d["detectorid"]: d["stationid"] for d in dprops
               if is_active(d) and d["stationid"] in stations}

    # --- PORTAL data, aggregated detector -> station -> hour ---------------
    rows = []
    for day in DAYS:
        end = (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        recs = fetch(f"freewaydata_{day}.json",
                     f"{API}/freewaydata/?start_date={day}&end_date={end}"
                     f"&resolution=01:00:00&format=json")
        for r in recs:
            sta = det2sta.get(r["detector_id"])
            if sta is None or not r.get("volume"):
                continue
            if r.get("speed") in (None, 0):
                continue
            rows.append((sta, pd.Timestamp(r["starttime"]).hour,
                         r["volume"], r["speed"]))
    df = pd.DataFrame(rows, columns=["sta", "hour", "vol", "mph"])
    print(f"detector-hour records kept: {len(df):,} over {len(DAYS)} days")

    def band(lo, hi):
        d = df[(df.hour >= lo) & (df.hour < hi)]
        g = d.groupby("sta").apply(
            lambda x: np.average(x.mph, weights=x.vol), include_groups=False)
        v = d.groupby("sta").vol.sum() / len(DAYS) / (hi - lo)
        return g, v

    day_mph, day_vph = band(9, 17)      # the average-hour comparison target
    am_mph, _ = band(7, 9)
    pm_mph, _ = band(16, 18)

    # --- the model side ----------------------------------------------------
    print(f"loading graph: {GRAPH}")
    G = ox.load_graphml(GRAPH)
    lat0 = math.radians(45.5)
    KX, KY = 111320 * math.cos(lat0), 110540

    # candidate mainline edges per ref, with local-meter geometry
    cand = {ref: [] for _, ref in REF_MAP}
    for u, v, k, d in G.edges(keys=True, data=True):
        hw = d.get("highway")
        hw = hw[0] if isinstance(hw, list) else hw
        if str(hw) != "motorway":
            continue
        refs = d.get("ref")
        refs = refs if isinstance(refs, list) else [refs]
        refs = [str(r) for r in refs if r]
        hit = next((ref for ref in cand if ref in refs), None)
        if hit is None:
            continue
        if "geometry" in d:
            pts = list(d["geometry"].coords)
        else:
            pts = [(G.nodes[u]["x"], G.nodes[u]["y"]),
                   (G.nodes[v]["x"], G.nodes[v]["y"])]
        xy = [(px * KX, py * KY) for px, py in pts]
        cand[hit].append(((u, v, k), xy))

    def snap(st):
        sx, sy = st["lon"] * KX, st["lat"] * KY
        ex, ey = DIR_VEC[st["dir"]]
        best, best_d = None, MAX_SNAP_M
        for key, xy in cand[st["ref"]]:
            # direction check on the edge's overall run
            dx, dy = xy[-1][0] - xy[0][0], xy[-1][1] - xy[0][1]
            n = math.hypot(dx, dy) or 1.0
            if (dx * ex + dy * ey) / n <= 0.2:
                continue
            # distance to the nearest vertex of the edge polyline
            d = min(math.hypot(px - sx, py - sy) for px, py in xy)
            if d < best_d:
                best, best_d = key, d
        return best, best_d

    # model speeds per edge, averaged over seeds
    frames = []
    for s in SEEDS:
        p = os.path.join(config.PROCESSED_DIR, f"{ARM}_s{s}_segments.parquet")
        if os.path.exists(p):
            frames.append(pd.read_parquet(p))
    seg = pd.concat(frames).groupby(["u", "v", "key"]).sum()
    seg["mph"] = 2.23694 * seg["v_sum"] / seg["value"].where(seg["value"] > 0)

    # --- the comparison ----------------------------------------------------
    out = []
    for sid, st in stations.items():
        if sid not in day_mph.index:
            continue
        key, dist = snap(st)
        if key is None:
            continue
        m = seg.loc[key, "mph"] if key in seg.index else np.nan
        if not np.isfinite(m):
            continue
        out.append({
            "sid": sid, "ref": st["ref"], "text": st["text"][:42],
            "edge": key, "day": day_mph[sid], "am": am_mph.get(sid, np.nan),
            "pm": pm_mph.get(sid, np.nan), "model": m,
            "ratio": m / day_mph[sid], "frozen": sid in FROZEN})
    res = pd.DataFrame(out).sort_values(["ref", "sid"])
    return res, seg, G, len(frames)


def main():
    res, seg, G, n_seeds = build()
    print(f"\nmodel = realized mean speed at the cited 16,500 demand "
          f"({n_seeds} seeds, corrected lanes)")
    print(f"real  = PORTAL volume-weighted station speed, {DAYS[0]}..{DAYS[-1]}")
    hdr = (f"{'station':<44}{'real day':>9}{'real AM':>8}{'real PM':>8}"
           f"{'model':>7}{'ratio':>7}")

    for ref, grp in res.groupby("ref"):
        print(f"\n--- {ref} ({len(grp)} stations) ---")
        print(hdr)
        for _, r in grp.iterrows():
            tag = "*" if r["frozen"] else " "
            print(f"{tag}{r['text']:<43}{r['day']:>8.1f}{r['am']:>8.1f}"
                  f"{r['pm']:>8.1f}{r['model']:>7.1f}{r['ratio']:>7.2f}")
        print(f"    corridor median: real day {grp['day'].median():.1f} mph, "
              f"model {grp['model'].median():.1f} mph, "
              f"ratio {grp['ratio'].median():.2f}")

    print(f"\n* = station in the Rose Quarter pre-registration's frozen set")
    print(f"\nOVERALL: {len(res)} stations matched; median model/real ratio "
          f"{res['ratio'].median():.2f}; stations where the model runs below "
          f"HALF the real daytime speed: {(res['ratio'] < 0.5).sum()} "
          f"({100 * (res['ratio'] < 0.5).mean():.0f}%)")


if __name__ == "__main__":
    main()
