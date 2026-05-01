"""
graph_definitions.py
--------------------
Defines the cross-layer ELD attack graph used in H1.

Graph structure (3 layers):
  Layer 1 — Wireless entry   : wifi_recon -> eld_firmware
  Layer 2 — Vehicle bus      : eld_firmware -> j1939_bus -> ecu_control
                               eld_firmware -> telematics_api  (alt path, bypasses bus)
  Layer 3 — Backend          : ecu_control -> telematics_api -> cloud_backend

Edge weights (p, d):
  p = transition probability  (attacker succeeds at this step)
  d = detection probability   (defender notices this step)

Sources for baseline values:
  Layer 1: Jepson et al. 2024 — demonstrated no-auth ELD exploitation over WiFi/BT
  Layer 2: Murvay & Groza 2018 (J1939 no message auth), Jichici et al. 2024 (IDS miss rates)
  Layer 3: No prior paper covers this — values are conservative assumptions,
           explicitly flagged as the research gap this work addresses.
"""

import json
import os
import networkx as nx


# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------

NODES = {
    "wifi_recon": {
        "layer": 1,
        "label": "WiFi recon",
        "description": "Attacker within WiFi/BT range of target truck",
    },
    "eld_firmware": {
        "layer": 1,
        "label": "ELD firmware access",
        "description": "Unauthorized firmware upload via exposed web interface (Jepson)",
    },
    "j1939_bus": {
        "layer": 2,
        "label": "J1939 bus injection",
        "description": "Attacker injects messages onto CAN bus (Murvay & Groza)",
    },
    "ecu_control": {
        "layer": 2,
        "label": "ECU control",
        "description": "Engine/brake ECU responds to injected commands (Jichici IDS miss rate)",
    },
    "telematics_api": {
        "layer": 3,
        "label": "Telematics API",
        "description": "Fleet management API — assumed weak auth (research gap)",
    },
    "cloud_backend": {
        "layer": 3,
        "label": "Cloud backend",
        "description": "Fleet HoS records, dispatch data, vehicle telemetry compromised",
    },
}


# ---------------------------------------------------------------------------
# Edge definitions
# ---------------------------------------------------------------------------
# Each edge: (source, target, {p, d, layer, source_paper, notes})
#
# 'p'            : float [0,1] — baseline transition probability
# 'd'            : float [0,1] — baseline detection probability
# 'layer'        : int — which defense layer this edge belongs to
# 'source_paper' : citation backing the probability estimate
# 'is_alt_path'  : bool — True for the direct ELD->telematics bypass

EDGES = [
    (
        "wifi_recon",
        "eld_firmware",
        {
            "p": 0.85,
            "d": 0.05,
            "layer": 1,
            "source_paper": "Jepson et al. 2024",
            "notes": (
                "Jepson demonstrated successful ELD exploitation in all tested attempts "
                "over open WiFi. 0.85 is conservative. Detection near zero — no "
                "logging on consumer ELD web interfaces."
            ),
            "is_alt_path": False,
        },
    ),
    (
        "eld_firmware",
        "j1939_bus",
        {
            "p": 0.90,
            "d": 0.10,
            "layer": 2,
            "source_paper": "Murvay & Groza 2018",
            "notes": (
                "J1939 has no message authentication — once on bus, injection "
                "succeeds unless Rogers et al. CAN Conditioners are present. "
                "Detection low without IDS."
            ),
            "is_alt_path": False,
        },
    ),
    (
        "j1939_bus",
        "ecu_control",
        {
            "p": 0.75,
            "d": 0.30,
            "layer": 2,
            "source_paper": "Jichici et al. 2024",
            "notes": (
                "d=0.30 reflects Jichici's best physics-aware IDS result. "
                "Pure ML detection was lower (~0.15). p=0.75 accounts for "
                "some ECUs rejecting out-of-range values."
            ),
            "is_alt_path": False,
        },
    ),
    (
        "eld_firmware",
        "telematics_api",
        {
            "p": 0.65,
            "d": 0.15,
            "layer": 3,
            "source_paper": "Research gap — assumed",
            "notes": (
                "Direct path from compromised ELD to fleet backend, bypassing "
                "the J1939 bus entirely. This is the key alt-path that single-layer "
                "bus defense cannot stop. Values are conservative assumptions."
            ),
            "is_alt_path": True,
        },
    ),
    (
        "ecu_control",
        "telematics_api",
        {
            "p": 0.60,
            "d": 0.20,
            "layer": 3,
            "source_paper": "Research gap — assumed",
            "notes": (
                "Attacker pivots from vehicle bus access to fleet backend "
                "via ELD's cellular uplink."
            ),
            "is_alt_path": False,
        },
    ),
    (
        "telematics_api",
        "cloud_backend",
        {
            "p": 0.70,
            "d": 0.10,
            "layer": 3,
            "source_paper": "Research gap — assumed",
            "notes": (
                "Fleet API to cloud backend. d=0.10 reflects typical API "
                "monitoring gaps in SME fleet operators."
            ),
            "is_alt_path": False,
        },
    ),
]


# ---------------------------------------------------------------------------
# Scenario modifiers
# ---------------------------------------------------------------------------

def apply_scenario(G: nx.DiGraph, scenario_name: str, config: dict) -> nx.DiGraph:
    """
    Return a copy of G with edge weights modified for the given scenario.

    Scenarios are defined in config.json and map to the three defense conditions:
      baseline     — no changes
      single_layer — Layer 2 detection raised (Rogers CAN Conditioners)
      cross_layer  — All layers' detection raised + Layer 1 transition penalized
    """
    G_scenario = G.copy()
    scenario = config["scenarios"][scenario_name]

    for u, v, data in G_scenario.edges(data=True):
        layer = data["layer"]

        if scenario_name == "baseline":
            pass  # no changes

        elif scenario_name == "single_layer":
            if layer == 2:
                data["d"] = scenario.get("layer2_detection_override", data["d"])

        elif scenario_name == "cross_layer":
            if layer == 1:
                data["d"] = scenario.get("layer1_detection_override", data["d"])
                # Cross-layer adds wireless auth check — reduces transition probability
                data["p"] = data["p"] * (1 - scenario.get("layer1_transition_penalty", 0))
            elif layer == 2:
                data["d"] = scenario.get("layer2_detection_override", data["d"])
            elif layer == 3:
                data["d"] = scenario.get("layer3_detection_override", data["d"])

    return G_scenario


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(config_path: str = None) -> tuple[nx.DiGraph, dict]:
    """
    Build and return the baseline attack graph plus loaded config

    Returns:
        G      : nx.DiGraph with all nodes and edges at baseline weights
        config : dict loaded from config.json
    """
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config.json"
        )

    with open(config_path) as f:
        config = json.load(f)

    G = nx.DiGraph()

    for node_id, attrs in NODES.items():
        G.add_node(node_id, **attrs)

    for src, dst, attrs in EDGES:
        # Store traversal cost from config
        edge_key = f"{src}->{dst}"
        cost = config["simulation"]["traversal_costs_minutes"].get(edge_key, 5)
        G.add_edge(src, dst, **attrs, cost_minutes=cost)

    return G, config


# ---------------------------------------------------------------------------
# Utility: enumerate all simple paths to the goal node
# ---------------------------------------------------------------------------

def get_all_attack_paths(G: nx.DiGraph) -> list[list[str]]:
    """Return all simple paths from wifi_recon to cloud_backend."""
    return list(nx.all_simple_paths(G, source="wifi_recon", target="cloud_backend"))


if __name__ == "__main__":
    G, config = build_graph()
    print(f"Nodes ({G.number_of_nodes()}): {list(G.nodes())}")
    print(f"Edges ({G.number_of_edges()}):")
    for u, v, d in G.edges(data=True):
        print(f"  {u} -> {v}  p={d['p']:.2f}  d={d['d']:.2f}  layer={d['layer']}")
    print("\nAttack paths:")
    for path in get_all_attack_paths(G):
        print(f"  {' -> '.join(path)}")