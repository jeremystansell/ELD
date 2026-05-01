# Cross-Layer ELD Attack Propagation Model

A Monte Carlo simulation demonstrating that single-layer ELD security monitoring is insufficient against cross-layer attacks. 
Attackers exploiting alternate paths can bypass monitored layers entirely, rendering single-layer defenses ineffective despite high detection rates.

## Hypothesis

**Single-layer ELD security monitoring is insufficient because attackers can exploit alternate paths that bypass monitored layers. Only cross-layer defense that correlates signals across WiFi/physical, CAN bus, and telematics layers can effectively reduce attack success.**

## Key Results

| Scenario     | Success Rate | Detection Rate | Change from Baseline |
|--------------|--------------|----------------|----------------------|
| Baseline     |    34.9%     |     28.9%      |          —           |
| Single-Layer |    34.9%     |     45.3%      | **0% reduction**     |
| Cross-Layer  |    21.2%     |     86.7%      | **-39% reduction**   |

Single-layer defense achieves 87.7% detection on Layer 2 (CAN bus) but **zero reduction** in attack success because 63% of attacks take the alt-path bypass that never traverses Layer 2.

## Architecture

### Attack Graph (H1)

Six nodes across three layers:

```
Layer 1 (Wireless Entry)     Layer 2 (Vehicle Bus)        Layer 3 (Backend)
┌─────────────┐              ┌─────────────┐              ┌─────────────-┐        ┌────────────-┐
│ wifi_recon  │──────────────│ eld_firmware│──────────────│telematics_api│────────│cloud_backend│
└─────────────┘              └──────┬──────┘              └─────────────-┘        └─────────────┘
                                    │                            ▲
                                    ▼                            │
                             ┌─────────────┐              ┌─────────────┐
                             │  j1939_bus  │──────────────│ ecu_control │
                             └─────────────┘              └─────────────┘

Alt-path (bypass): eld_firmware ──────────────────────────► telematics_api (skips Layer 2)
```

### Worm Propagation (H3)

SIR epidemic model simulating worm spread across truck fleet at a truck stop. Infected truck count feeds H1 as the attack entry rate.

### Literature Grounding

| Layer   | Parameter | Value                     | Source                 |
|---------|-----------|---------------------------|------------------------|
| Layer 1 | p=0.85    | WiFi exploitation success | Jepson et al. 2024     |
| Layer 2 | p=0.90    | J1939 injection (no auth) | Murvay & Groza 2018    |
| Layer 2 | d=0.30    | Best IDS detection rate   | Jichici et al. 2024    |
| Layer 3 | p, d      | Conservative assumptions  | Research gap (flagged) |

## Setup

**Requirements:** Python 3.11+ (tested on 3.13)

```bash
git clone <repo-url>
cd Cross-layer-ELD-attack-propagation-model-using-NetworkX-and-Monte-Carlo

# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1

# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Running the Simulation

### Full Pipeline (Recommended)

```bash
python run_all.py
```

This runs:
1. H3 worm propagation         → `outputs/worm_output.json`
2. H1 attack graph Monte Carlo → `outputs/simulation_results.json`
3. Figure generation           → `outputs/figures/`

### Step-by-Step

```bash
# Verify graph structure
python h1_attack_graph/graph_definitions.py

# Run H3 worm simulation
python h3_worm/run_worm.py

# Run H1 Monte Carlo (uses worm output as entry rate)
python h1_attack_graph/run_simulation.py

# Generate all figures
python figures/generate_all.py
```

### Running Tests

```bash
pytest tests/ -v
```

## Output Figures

| Figure                         | Description                              |
|--------------------------------|------------------------------------------|
| `fig1_scenario_comparison.png` | Success vs detection rate bar chart      |
| `fig2_worm_propagation.png`    | SIR curves for H3 worm spread            |
| `fig3_layer_detection.png`     | Per-layer detection rate heatmap         |
| `fig4_path_frequencies.png`    | Attack path selection (main vs alt-path) |
| `fig5_ttc_cdf.png`             | CDF of time-to-compromise                |
| `fig6_sensitivity.png`         | Sensitivity analysis varying Layer 3 p   |

## Sensitivity Analysis

Layer 3 parameters are explicitly flagged as research gaps. The sensitivity analysis shows cross-layer advantage holds across all reasonable assumptions:

| Layer 3 p | Baseline | Single-Layer | Cross-Layer |
|-----------|----------|--------------|-------------|
|   0.50    | 17.5%    | 17.5%        | 11.0%       |
|   0.60    | 25.3%    | 25.3%        | 15.9%       |
|   0.70    | 34.9%    | 34.9%        | 20.4%       |
|   0.80    | 45.4%    | 45.4%        | 26.7%       |
|   0.90    | 58.6%    | 58.6%        | 34.9%       |

Baseline and single-layer are **identical** across all values — confirming the alt-path bypass renders single-layer defense ineffective regardless of Layer 3 assumptions.

## Configuration

All parameters are in `config.json`:

```json
{
  "simulation": {
    "n_trials": 10000,
    "random_seed": 42,
    "traversal_costs_minutes": { ... }
  },
  "scenarios": {
    "baseline": { ... },
    "single_layer": { "layer2_detection_override": 0.85 },
    "cross_layer": { 
      "layer1_detection_override": 0.75,
      "layer2_detection_override": 0.85,
      "layer3_detection_override": 0.70,
      "layer1_transition_penalty": 0.40
    }
  },
  "worm": {
    "fleet_size": 50,
    "wifi_radius_m": 30,
    "beta": 0.3,
    "gamma": 0.05
  }
}
```

## Project Structure

```
├── config.json                 # Shared parameters
├── requirements.txt
├── run_all.py                  # Full pipeline runner
├── h1_attack_graph/
│   ├── graph_definitions.py    # Attack graph nodes, edges, probabilities
│   ├── monte_carlo.py          # Monte Carlo simulation engine
│   └── run_simulation.py       # H1 entry point
├── h3_worm/
│   ├── worm_model.py           # SIR epidemic model
│   └── run_worm.py             # H3 entry point
├── figures/
│   └── generate_all.py         # All six figures
├── outputs/                    # Generated outputs (gitignored)
│   ├── worm_output.json
│   ├── simulation_results.json
│   └── figures/
└── tests/
    └── tests_graph.py          # Unit tests
```

## Key Findings

1. **Single-layer detection ≠ blocking**: 87.7% Layer 2 detection with 0% success reduction
2. **Alt-path dominates**: 63% of attacks bypass the monitored layer entirely
3. **Detection without blocking is security theater**: "Detected and succeeded" rate *increases* with single-layer defense
4. **Cross-layer is required**: Only all-layer correlation reduces actual compromise rate
5. **Results are robust**: Sensitivity analysis confirms findings hold across Layer 3 uncertainty

## References

- Jepson et al.  2024 — ELD WiFi exploitation demonstration
- Murvay & Groza 2018 — J1939 protocol security analysis
- Jichici et al. 2024 — Physics-aware CAN bus IDS
- Rogers et al.       — CAN Conditioner defense mechanism
