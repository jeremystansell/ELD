"""
run_worm.py
-----------
Entry point for H2 worm propagation simulation.
Runs all three policy scenarios and writes outputs/worm_output.json.

Usage:
    python h2_worm/run_worm.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from worm_model import run_all_policies

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "outputs", "worm_output.json")


def main():
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    print("Running H2 worm propagation simulation...")
    results = run_all_policies(config)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nWorm output saved to {OUTPUT_PATH}")
    print("This file is consumed by H1 monte_carlo.py as the attack entry rate.")


if __name__ == "__main__":
    main()