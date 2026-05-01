#entry point, reads H3 output or runs standalone
"""
run_simulation.py
-----------------
Entry point for H1 cross-layer attack graph simulation.
Reads H3 worm output if available, otherwise runs standalone.

Usage:
    # Standalone (no H2 integration):
    python h1_attack_graph/run_simulation.py

    # With H2 worm output feeding entry rate:
    python h1_attack_graph/run_simulation.py --worm outputs/worm_output.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from monte_carlo import run_all_scenarios

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "outputs", "simulation_results.json")


def main():
    parser = argparse.ArgumentParser(description="Run H1 attack graph simulation")
    parser.add_argument(
        "--worm",
        type=str,
        default=None,
        help="Path to worm_output.json from H3 (optional)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Override number of trials (default: from config.json)",
    )
    args = parser.parse_args()

    # If worm path not specified, check if default output exists
    worm_path = args.worm
    default_worm = os.path.join(os.path.dirname(__file__), "..", "outputs", "worm_output.json")
    if worm_path is None and os.path.exists(default_worm):
        print(f"Found H2 worm output at {default_worm} — using as entry rate input.")
        worm_path = default_worm
    elif worm_path is None:
        print("No worm output found — running H1 standalone with fixed trial rate.")

    print("\nRunning H1 cross-layer attack graph simulation...")
    results = run_all_scenarios(
        config_path=CONFIG_PATH,
        worm_output_path=worm_path,
        output_path=OUTPUT_PATH,
    )

    print("\n" + "=" * 55)
    print(f"{'Scenario':<20} {'Success':>10} {'Detected':>10} {'Mean TTC':>10}")
    print("-" * 55)
    for name, r in results.items():
        print(
            f"{name:<20} "
            f"{r.success_rate:>9.1%} "
            f"{r.detection_rate:>9.1%} "
            f"{r.mean_time_to_compromise:>8.1f}m"
        )
    print("=" * 55)
    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()