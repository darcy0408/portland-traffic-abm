"""Re-download the metro street graph WITH the lane tags OSMnx drops by default.

Why this exists: src/lane_tag_survey.py showed the cached 20 km graph carries
`lanes` on only 67% of arterial edges and carries `lanes:forward`,
`lanes:backward` and `turn:lanes` on NONE of them. Those tags are not missing
from OpenStreetMap; OSMnx's default `useful_tags_way` list never requests them.
Without them the model cannot know a two-way arterial's real directional split,
so `_parse_lanes` halves the total and floors it, turning a 3-lane street into
one lane per direction. That affects 20.5% of two-way tagged arterials.

This script downloads the same study area with a widened tag list and caches it
under a NEW filename, so the existing graph and every result computed from it
stay exactly where they are.

Run it once:
    python src/build_capacity_graph.py

Downloads are slow (the 20 km metro area is ~160k directed edges), which is why
the result is cached and never re-fetched.
"""
import os
import sys
import time

import osmnx as ox

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config

OUT_NAME = "graph_metro20k_lanes.graphml"

# OSMnx's default way-tag list, plus every tag needed to reconstruct a real
# per-direction lane count and the turn pockets that set intersection discharge.
# Superset of the default: nothing the existing pipeline reads is dropped.
LANE_TAGS = [
    # --- OSMnx defaults, kept so nothing downstream loses an attribute ---
    "bridge", "tunnel", "oneway", "lanes", "ref", "name", "highway",
    "maxspeed", "service", "access", "area", "landuse", "width", "est_width",
    "junction",
    # --- the directional split: which way those lanes actually run ---
    "lanes:forward", "lanes:backward", "lanes:both_ways",
    # --- turn pockets: a dedicated left-turn lane changes how many vehicles an
    #     intersection can discharge per green, which is the real capacity knob ---
    "turn:lanes", "turn:lanes:forward", "turn:lanes:backward",
    # --- lanes that do not carry general traffic and must not be counted ---
    "bus:lanes", "psv:lanes", "hov", "hov:lanes", "cycleway", "parking:lane:both",
    "parking:lane:left", "parking:lane:right",
]


def main():
    out = os.path.join(config.NETWORK_DIR, OUT_NAME)
    if os.path.exists(out):
        print(f"already cached: {out}")
        return

    os.makedirs(config.NETWORK_DIR, exist_ok=True)

    # OSMnx moved this setting between major versions; support both.
    if hasattr(ox, "settings"):
        ox.settings.useful_tags_way = LANE_TAGS
        ox.settings.use_cache = True
    else:                                     # OSMnx < 1.0
        ox.config(useful_tags_way=LANE_TAGS, use_cache=True)

    print(f"osmnx {ox.__version__}")
    print(f"downloading {config.STUDY_RADIUS_M} m around {config.STUDY_CENTER} "
          f"({config.NETWORK_TYPE}) with {len(LANE_TAGS)} way tags")
    t0 = time.time()
    G = ox.graph_from_point(config.STUDY_CENTER, dist=config.STUDY_RADIUS_M,
                            network_type=config.NETWORK_TYPE)
    print(f"got {G.number_of_nodes():,} nodes / {G.number_of_edges():,} edges "
          f"in {time.time() - t0:.0f}s")

    ox.save_graphml(G, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
