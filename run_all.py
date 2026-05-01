"""
run_all.py
----------
Runs the full simulation pipeline in order:
  1. H2 worm propagation  -> outputs/worm_output.json
  2. H1 attack graph      -> outputs/simulation_results.json
  3. All four figures     -> outputs/figures/

Usage:
    python run_all.py
"""

import subprocess
import sys
import os

STEPS = [
    ("H2 — Worm propagation",       ["h2_worm/run_worm.py"]),
    ("H1 — Attack graph simulation", ["h1_attack_graph/run_simulation.py"]),
    ("Figures — Generate all",       ["figures/generate_all.py"]),
]

def main():
    os.makedirs("outputs/figures", exist_ok=True)

    for label, script_args in STEPS:
        print(f"\n{'='*55}")
        print(f"  {label}")
        print(f"{'='*55}")
        result = subprocess.run(
            [sys.executable] + script_args,
            check=False,
        )
        if result.returncode != 0:
            print(f"\nERROR: step '{label}' failed with exit code {result.returncode}")
            print("Fix the error above before continuing.")
            sys.exit(result.returncode)

    print(f"\n{'='*55}")
    print("  All steps completed successfully.")
    print(f"  Figures saved to outputs/figures/")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()