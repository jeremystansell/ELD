"""
worm_model.py
-------------
SIR epidemic model for ELD worm propagation across a truck-stop fleet.

Models Jepson's truck-to-truck WiFi worm vector in a spatial setting.
Trucks are placed in a truck-stop layout; 
infection spreads between trucks within WiFi range of an already-infected truck.

States:
  S — Susceptible  : uninfected, vulnerable ELD
  I — Infected     : ELD compromised, actively spreading worm
  R — Recovered    : patched or rebooted, no longer infectious

Output:
  Writes outputs/worm_output.json with time series data consumed by H1.
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, asdict

import numpy as np


# ---------------------------------------------------------------------------
# Truck agent
# ---------------------------------------------------------------------------

@dataclass
class Truck:
    truck_id: int
    x: float          # position in meters
    y: float
    state: str        # 'S', 'I', or 'R'
    infected_at: float | None = None
    recovered_at: float | None = None


# ---------------------------------------------------------------------------
# Truck-stop spatial layout
# ---------------------------------------------------------------------------

def generate_truckstop_layout(n_trucks: int, rng: np.random.Generator) -> list[Truck]:
    """
    Place trucks in a realistic truck-stop grid layout.
    Two rows of parking spots, ~4m wide x 20m long each, with a lane between.
    Total lot: ~200m x 80m for up to 50 trucks.
    """
    trucks = []
    spots_per_row = max(n_trucks // 2, 1)

    for i in range(n_trucks):
        row = i % 2
        col = i // 2
        # x: spread along lot length, slight random offset for realism
        x = 10 + col * (200 / max(spots_per_row, 1)) + rng.uniform(-2, 2)
        # y: two rows separated by a 20m lane
        y = 15 + row * 50 + rng.uniform(-1, 1)
        trucks.append(Truck(truck_id=i, x=x, y=y, state="S"))

    return trucks


# ---------------------------------------------------------------------------
# Core SIR model
# ---------------------------------------------------------------------------

class WormModel:
    """
    Spatial SIR model for ELD worm propagation.

    At each timestep:
      1. Each Infected truck attempts to infect each Susceptible truck
         within wifi_radius_m. Infection probability scales with beta.
      2. Each Infected truck recovers with probability gamma (patched/rebooted).
      3. Recovered trucks can be re-infected if patch_rate < 1 (partial patching).

    Policy variants controlled by config:
      baseline       — no intervention
      ssid_isolation — reduces effective wifi_radius by 60% (network segmentation)
      patch_rate     — proportion of trucks with auto-update enabled
    """

    def __init__(self, config: dict, policy: str = "baseline", rng_seed: int = 42):
        self.config = config
        self.policy = policy
        worm_cfg = config["worm"]

        self.n_trucks = worm_cfg["fleet_size"]
        self.beta = worm_cfg["beta"]
        self.gamma = worm_cfg["gamma"]
        self.patch_rate = worm_cfg["patch_rate"]
        self.sim_duration = worm_cfg["sim_duration_minutes"]
        self.dt = 1.0  # 1-minute timesteps

        self.wifi_radius = worm_cfg["wifi_radius_m"]
        if policy == "ssid_isolation":
            # SSID isolation reduces effective range significantly
            self.wifi_radius *= 0.4

        self.rng = np.random.default_rng(rng_seed)
        self.trucks = generate_truckstop_layout(self.n_trucks, self.rng)

        # Seed one infected truck (patient zero — attacker's initial target)
        patient_zero = self.rng.integers(0, self.n_trucks)
        self.trucks[patient_zero].state = "I"
        self.trucks[patient_zero].infected_at = 0.0

    def _distance(self, t1: Truck, t2: Truck) -> float:
        return np.sqrt((t1.x - t2.x) ** 2 + (t1.y - t2.y) ** 2)

    def _neighbors_in_range(self, truck: Truck) -> list[Truck]:
        return [
            t for t in self.trucks
            if t.truck_id != truck.truck_id
            and self._distance(truck, t) <= self.wifi_radius
        ]

    def step(self, t: float) -> None:
        """Advance simulation by one timestep."""
        new_states = {tr.truck_id: tr.state for tr in self.trucks}

        for truck in self.trucks:
            if truck.state == "I":
                # Attempt infection of susceptible neighbors
                for neighbor in self._neighbors_in_range(truck):
                    if neighbor.state == "S":
                        if self.rng.random() < self.beta * self.dt:
                            new_states[neighbor.truck_id] = "I"
                            neighbor.infected_at = t

                # Recovery / patching
                recovery_prob = self.gamma
                if self.policy == "patch_rate":
                    recovery_prob = self.gamma + self.patch_rate
                if self.rng.random() < recovery_prob * self.dt:
                    new_states[truck.truck_id] = "R"
                    truck.recovered_at = t

        for truck in self.trucks:
            truck.state = new_states[truck.truck_id]

    def run(self) -> dict:
        """
        Run full simulation and return time series dict.

        Returns:
            dict with keys:
              t_minutes    : list of timestep values
              n_susceptible: list of S counts per timestep
              n_infected   : list of I counts per timestep
              n_recovered  : list of R counts per timestep
              policy       : policy name
              final_infected_pct: float
        """
        timesteps = int(self.sim_duration / self.dt)
        t_minutes = []
        n_s, n_i, n_r = [], [], []

        for step_idx in range(timesteps):
            t = step_idx * self.dt
            t_minutes.append(t)

            counts = {"S": 0, "I": 0, "R": 0}
            for truck in self.trucks:
                counts[truck.state] += 1
            n_s.append(counts["S"])
            n_i.append(counts["I"])
            n_r.append(counts["R"])

            self.step(t)

        final_infected_pct = (n_i[-1] + n_r[-1]) / self.n_trucks

        return {
            "t_minutes": t_minutes,
            "n_susceptible": n_s,
            "n_infected": n_i,
            "n_recovered": n_r,
            "n_trucks": self.n_trucks,
            "policy": self.policy,
            "wifi_radius_m": self.wifi_radius,
            "final_infected_pct": round(final_infected_pct, 4),
            "peak_infected": max(n_i),
            "peak_infected_t": t_minutes[n_i.index(max(n_i))],
        }


# ---------------------------------------------------------------------------
# Run all three policy scenarios
# ---------------------------------------------------------------------------

def run_all_policies(config: dict) -> dict[str, dict]:
    """Run baseline, ssid_isolation, and patch_rate policies."""
    seed = config["simulation"]["random_seed"]
    results = {}
    for policy in ("baseline", "ssid_isolation", "patch_rate"):
        print(f"  Running worm simulation: policy={policy}")
        model = WormModel(config, policy=policy, rng_seed=seed)
        results[policy] = model.run()
        r = results[policy]
        print(f"    Peak infected: {r['peak_infected']}/{r['n_trucks']} "
              f"trucks at t={r['peak_infected_t']:.0f} min")
    return results


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    with open(config_path) as f:
        config = json.load(f)

    results = run_all_policies(config)
    for policy, r in results.items():
        print(f"\n{policy}: peak={r['peak_infected']} trucks, "
              f"final infected={r['final_infected_pct']:.1%}")