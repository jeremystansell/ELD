"""
monte_carlo.py
--------------
Monte Carlo simulation engine for the H1 cross-layer ELD attack graph.

Each trial:
  1. Selects an attack path probabilistically (paths with higher cumulative p
     are selected more often — reflects a rational attacker choosing best route)
  2. Traverses each edge on the selected path, sampling transition and detection
  3. Records: success/fail, detected/undetected, time-to-compromise, path taken,
     which node the attack died at (if blocked)

Key design decisions:
  - Detection and blocking are INDEPENDENT. An attacker can be detected but
    still succeed — detection without cross-layer blocking doesn't stop the attack.
    This is intentional and supports the paper's main argument.
  - Time-to-compromise accumulates edge traversal costs even when detection occurs,
    because a real defender still needs to respond.
  - H3 integration: if worm_output is provided, the per-timestep trial rate scales
    with the number of infected trucks, creating a realistic entry funnel.
  - TODO Remove debug flags
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import networkx as nx

from graph_definitions import build_graph, apply_scenario, get_all_attack_paths


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TrialResult:
    """Outcome of a single Monte Carlo trial."""
    trial_id: int
    scenario: str
    success: bool               # reached cloud_backend
    detected: bool              # flagged by any detection check (independent of success)
    time_to_compromise: float   # minutes (0 if blocked before reaching goal)
    path_taken: list            # list of node names
    blocked_at: str | None      # node where attack stopped (None if success)
    edges_traversed: list       # list of (src, dst) tuples actually crossed
    detection_events: list      # list of (src, dst) where detection fired


@dataclass
class ScenarioResults:
    """Aggregated results for one scenario across all trials."""
    scenario: str
    n_trials: int
    success_rate: float
    detection_rate: float
    detection_without_block_rate: float   # detected but still succeeded
    mean_time_to_compromise: float        # over successful trials only
    p95_time_to_compromise: float
    path_frequencies: dict = field(default_factory=dict)
    edge_traversal_counts: dict = field(default_factory=dict)
    blocked_at_counts: dict = field(default_factory=dict)
    layer_detection_rates: dict = field(default_factory=dict)
    raw_trials: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Path selection
# ---------------------------------------------------------------------------

def compute_path_weights(G: nx.DiGraph, paths: list[list[str]]) -> np.ndarray:
    """
    Assign selection weight to each path proportional to its cumulative
    transition probability. Rational attacker prefers the higghest-p path
    """
    weights = []
    for path in paths:
        cumulative_p = 1.0
        for i in range(len(path) - 1):
            edge_data = G.edges[path[i], path[i + 1]]
            cumulative_p *= edge_data["p"]
        weights.append(cumulative_p)

    weights = np.array(weights)
    total = weights.sum()
    return weights / total if total > 0 else np.ones(len(paths)) / len(paths)


# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------

def run_trial(
    G: nx.DiGraph,
    paths: list[list[str]],
    path_weights: np.ndarray,
    rng: np.random.Generator,
    trial_id: int,
    scenario: str,
) -> TrialResult:
    """Execute one Monte Carlo trial."""

    # Select path
    path_idx = rng.choice(len(paths), p=path_weights)
    path = paths[path_idx]

    success = False
    detected = False
    elapsed = 0.0
    blocked_at = None
    edges_traversed = []
    detection_events = []

    for i in range(len(path) - 1):
        src, dst = path[i], path[i + 1]
        edge = G.edges[src, dst]

        r_transition = rng.random()
        r_detection = rng.random()

        # Detection check (independent of whether transition succeeds)
        if r_detection < edge["d"]:
            detected = True
            detection_events.append((src, dst))

        # Transition check
        if r_transition >= edge["p"]:
            # Attack blocked at this edge
            blocked_at = dst
            break

        # Transition succeeded
        edges_traversed.append((src, dst))
        elapsed += edge.get("cost_minutes", 5)

        if dst == "cloud_backend":
            success = True
            break

    return TrialResult(
        trial_id=trial_id,
        scenario=scenario,
        success=success,
        detected=detected,
        time_to_compromise=elapsed if success else 0.0,
        path_taken=path,
        blocked_at=blocked_at,
        edges_traversed=edges_traversed,
        detection_events=detection_events,
    )


# ---------------------------------------------------------------------------
# Full scenario run
# ---------------------------------------------------------------------------

def run_scenario(
    G_base: nx.DiGraph,
    config: dict,
    scenario_name: str,
    n_trials: int = None,
    worm_output: dict = None,
) -> ScenarioResults:
    """
    Run all trials for one scenario and return aggregated results.

    Args:
        G_base       : baseline graph (will be copied and modified per scenario)
        config       : loaded config.json dict
        scenario_name: one of 'baseline', 'single_layer', 'cross_layer'
        n_trials     : override trial count (defaults to config value)
        worm_output  : optional H3 output dict with keys 't_minutes', 'n_infected'
                       If provided, trial launch rate scales with worm spread.
    """
    seed = config["simulation"]["random_seed"]
    rng = np.random.default_rng(seed)

    if n_trials is None:
        n_trials = config["simulation"]["n_trials"]

    G = apply_scenario(G_base, scenario_name, config)
    paths = get_all_attack_paths(G)
    path_weights = compute_path_weights(G, paths)

    # H2 integration: build per-trial entry rate multiplier
    if worm_output is not None:
        trial_weights = _build_worm_trial_weights(worm_output, n_trials)
    else:
        trial_weights = np.ones(n_trials)

    raw_trials = []
    print(f"  Running {n_trials:,} trials for scenario: {scenario_name}...")
    t0 = time.time()

    for i in range(n_trials):
        # Skip trial with probability proportional to inverse worm spread
        # (early trials less likely when worm hasn't spread yet)
        if worm_output is not None:
            if rng.random() > trial_weights[i]:
                continue

        result = run_trial(G, paths, path_weights, rng, trial_id=i, scenario=scenario_name)
        raw_trials.append(result)

    elapsed_wall = time.time() - t0
    print(f"  Done in {elapsed_wall:.1f}s — {len(raw_trials):,} trials executed")

    return _aggregate(raw_trials, scenario_name, G)


def _build_worm_trial_weights(worm_output: dict, n_trials: int) -> np.ndarray:
    """
    Map H3 worm infection curve onto trial indices.
    Trials later in the sequence are more likely to fire (more infected trucks = 
    more concurrent attack attempts).
    """
    n_infected = np.array(worm_output["n_infected"], dtype=float)
    n_infected_norm = n_infected / max(n_infected.max(), 1)
    # Stretch/compress worm timeline to match n_trials
    indices = np.linspace(0, len(n_infected_norm) - 1, n_trials)
    weights = np.interp(indices, np.arange(len(n_infected_norm)), n_infected_norm)
    # Clamp to [0.05, 1.0] so even early trials have a small chance
    return np.clip(weights, 0.05, 1.0)


def _aggregate(raw_trials: list[TrialResult], scenario_name: str, G: nx.DiGraph) -> ScenarioResults:
    """Compute summary statistics from raw trial list."""
    n = len(raw_trials)
    if n == 0:
        raise ValueError("No trials were executed — check worm_output or trial count.")

    successes = [t for t in raw_trials if t.success]
    detected = [t for t in raw_trials if t.detected]
    detected_and_succeeded = [t for t in raw_trials if t.detected and t.success]

    success_rate = len(successes) / n
    detection_rate = len(detected) / n
    detection_without_block_rate = len(detected_and_succeeded) / n

    times = [t.time_to_compromise for t in successes]
    mean_ttc = float(np.mean(times)) if times else 0.0
    p95_ttc = float(np.percentile(times, 95)) if times else 0.0

    # Path frequency
    path_freq = {}
    for t in raw_trials:
        key = " -> ".join(t.path_taken)
        path_freq[key] = path_freq.get(key, 0) + 1
    path_freq = {k: v / n for k, v in path_freq.items()}

    # Edge traversal counts (for heatmap figure)
    edge_counts = {}
    for t in successes:
        for edge in t.edges_traversed:
            key = f"{edge[0]}->{edge[1]}"
            edge_counts[key] = edge_counts.get(key, 0) + 1
    edge_counts = {k: v / max(len(successes), 1) for k, v in edge_counts.items()}

    # Blocked-at node counts
    blocked_counts = {}
    for t in raw_trials:
        if t.blocked_at:
            blocked_counts[t.blocked_at] = blocked_counts.get(t.blocked_at, 0) + 1

    # Per-layer detection rates
    layer_det = {1: [], 2: [], 3: []}
    for t in raw_trials:
        for edge in t.detection_events:
            layer = G.edges[edge[0], edge[1]]["layer"]
            layer_det[layer].append(1)
        # Edges traversed without detection contribute 0
        for edge in t.edges_traversed:
            layer = G.edges[edge[0], edge[1]]["layer"]
            if (edge[0], edge[1]) not in [(e[0], e[1]) for e in
                                           [(x, y) for x, y in t.detection_events]]:
                layer_det[layer].append(0)
    layer_det_rates = {
        f"layer_{k}": (sum(v) / max(len(v), 1)) for k, v in layer_det.items()
    }

    return ScenarioResults(
        scenario=scenario_name,
        n_trials=n,
        success_rate=success_rate,
        detection_rate=detection_rate,
        detection_without_block_rate=detection_without_block_rate,
        mean_time_to_compromise=mean_ttc,
        p95_time_to_compromise=p95_ttc,
        path_frequencies=path_freq,
        edge_traversal_counts=edge_counts,
        blocked_at_counts=blocked_counts,
        layer_detection_rates=layer_det_rates,
        raw_trials=raw_trials,
    )


# ---------------------------------------------------------------------------
# Entry point: run all three scenarios and save results
# ---------------------------------------------------------------------------

def run_all_scenarios(
    config_path: str = None,
    worm_output_path: str = None,
    output_path: str = None,
) -> dict[str, ScenarioResults]:

    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__), "..", "outputs", "simulation_results.json"
        )

    G, config = build_graph(config_path)

    worm_output = None
    if worm_output_path and os.path.exists(worm_output_path):
        print(f"Loading H3 worm output from {worm_output_path}")
        with open(worm_output_path) as f:
            raw = json.load(f)
        # worm_output.json is keyed by policy — use baseline as the entry rate
        worm_output = raw.get("baseline", raw)

    results = {}
    for scenario in ("baseline", "single_layer", "cross_layer"):
        results[scenario] = run_scenario(G, config, scenario, worm_output=worm_output)

    # Serialize (excluding raw_trials for file size)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    serializable = {}
    for name, r in results.items():
        d = asdict(r)
        d.pop("raw_trials")  # too large to serialize; kept in memory
        serializable[name] = d

    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    results = run_all_scenarios()
    for name, r in results.items():
        print(f"\n{'='*50}")
        print(f"Scenario: {name}")
        print(f"  Success rate:                 {r.success_rate:.1%}")
        print(f"  Detection rate:               {r.detection_rate:.1%}")
        print(f"  Detected but still succeeded: {r.detection_without_block_rate:.1%}")
        print(f"  Mean time-to-compromise:      {r.mean_time_to_compromise:.1f} min")
        print(f"  95th pct time-to-compromise:  {r.p95_time_to_compromise:.1f} min")
        print(f"  Layer detection rates:        {r.layer_detection_rates}")