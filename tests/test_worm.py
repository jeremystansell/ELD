"""
tests/test_worm.py
------------------
Unit tests for H2 worm propagation model.

Run with:
    pytest tests/test_worm.py -v
"""

from __future__ import annotations

import json
import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "h2_worm"))
from worm_model import WormModel, generate_truckstop_layout, Truck

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


@pytest.fixture
def config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


@pytest.fixture
def baseline_model(config):
    return WormModel(config, policy="baseline", rng_seed=42)


# ---------------------------------------------------------------------------
# Layout tests
# ---------------------------------------------------------------------------

class TestLayout:

    def test_correct_truck_count(self, config):
        rng = np.random.default_rng(42)
        n = config["worm"]["fleet_size"]
        trucks = generate_truckstop_layout(n, rng)
        assert len(trucks) == n

    def test_trucks_have_unique_ids(self, config):
        rng = np.random.default_rng(42)
        trucks = generate_truckstop_layout(config["worm"]["fleet_size"], rng)
        ids = [t.truck_id for t in trucks]
        assert len(ids) == len(set(ids))

    def test_trucks_have_valid_positions(self, config):
        rng = np.random.default_rng(42)
        trucks = generate_truckstop_layout(config["worm"]["fleet_size"], rng)
        for t in trucks:
            assert t.x >= 0
            assert t.y >= 0

    def test_all_trucks_start_susceptible(self, config):
        rng = np.random.default_rng(99)
        trucks = generate_truckstop_layout(10, rng)
        for t in trucks:
            assert t.state == "S"


# ---------------------------------------------------------------------------
# Model initialization tests
# ---------------------------------------------------------------------------

class TestModelInit:

    def test_patient_zero_exists(self, baseline_model):
        infected = [t for t in baseline_model.trucks if t.state == "I"]
        assert len(infected) == 1, "Should start with exactly one infected truck"

    def test_correct_fleet_size(self, baseline_model, config):
        assert len(baseline_model.trucks) == config["worm"]["fleet_size"]

    def test_ssid_isolation_reduces_radius(self, config):
        base = WormModel(config, policy="baseline", rng_seed=42)
        isolated = WormModel(config, policy="ssid_isolation", rng_seed=42)
        assert isolated.wifi_radius < base.wifi_radius

    def test_baseline_radius_matches_config(self, config, baseline_model):
        assert baseline_model.wifi_radius == config["worm"]["wifi_radius_m"]


# ---------------------------------------------------------------------------
# Simulation run tests
# ---------------------------------------------------------------------------

class TestSimulationRun:

    def test_run_returns_expected_keys(self, baseline_model):
        result = baseline_model.run()
        expected_keys = {"t_minutes", "n_susceptible", "n_infected",
                         "n_recovered", "policy", "final_infected_pct",
                         "peak_infected", "peak_infected_t"}
        assert expected_keys.issubset(result.keys())

    def test_time_series_lengths_match(self, baseline_model):
        result = baseline_model.run()
        n = len(result["t_minutes"])
        assert len(result["n_susceptible"]) == n
        assert len(result["n_infected"]) == n
        assert len(result["n_recovered"]) == n

    def test_population_conserved(self, config):
        model = WormModel(config, policy="baseline", rng_seed=42)
        result = model.run()
        n_trucks = config["worm"]["fleet_size"]
        for i in range(len(result["t_minutes"])):
            total = (result["n_susceptible"][i] +
                     result["n_infected"][i] +
                     result["n_recovered"][i])
            assert total == n_trucks, f"Population not conserved at t={result['t_minutes'][i]}"

    def test_infection_spreads(self, config):
        """Worm should infect more than just patient zero over time."""
        model = WormModel(config, policy="baseline", rng_seed=42)
        result = model.run()
        assert max(result["n_infected"]) > 1, "Worm never spread beyond patient zero"

    def test_infection_starts_at_one(self, config):
        model = WormModel(config, policy="baseline", rng_seed=42)
        result = model.run()
        assert result["n_infected"][0] == 1

    def test_final_infected_pct_in_range(self, config):
        model = WormModel(config, policy="baseline", rng_seed=42)
        result = model.run()
        assert 0.0 <= result["final_infected_pct"] <= 1.0

    def test_ssid_isolation_reduces_spread(self, config):
        """SSID isolation should result in fewer total infections than baseline."""
        base = WormModel(config, policy="baseline", rng_seed=42)
        isolated = WormModel(config, policy="ssid_isolation", rng_seed=42)
        r_base = base.run()
        r_iso = isolated.run()
        assert r_iso["peak_infected"] <= r_base["peak_infected"], \
            "SSID isolation did not reduce peak infections vs baseline"

    def test_reproducible_with_same_seed(self, config):
        m1 = WormModel(config, policy="baseline", rng_seed=42)
        m2 = WormModel(config, policy="baseline", rng_seed=42)
        r1 = m1.run()
        r2 = m2.run()
        assert r1["peak_infected"] == r2["peak_infected"]
        assert r1["final_infected_pct"] == r2["final_infected_pct"]

    def test_peak_infected_t_is_valid_timestep(self, config):
        model = WormModel(config, policy="baseline", rng_seed=42)
        result = model.run()
        assert result["peak_infected_t"] in result["t_minutes"]