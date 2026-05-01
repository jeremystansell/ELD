"""
figures/generate_all.py
-----------------------
Generate all figures from simulation outputs.

Outputs:
  - outputs/figures/fig1_scenario_comparison.png
  - outputs/figures/fig2_worm_propagation.png
  - outputs/figures/fig3_layer_detection.png
  - outputs/figures/fig4_path_frequencies.png
  - outputs/figures/fig5_ttc_cdf.png
  - outputs/figures/fig6_sensitivity.png
"""

import json
import os
import sys

import matplotlib.pyplot as plt
import numpy as np

SCRIPT_DIR = os.path.dirname(__file__)
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "outputs", "figures")
SIM_RESULTS_PATH = os.path.join(SCRIPT_DIR, "..", "outputs", "simulation_results.json")
WORM_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "outputs", "worm_output.json")
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "config.json")

sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "h1_attack_graph"))
from graph_definitions import build_graph
from monte_carlo import run_scenario


def load_data():
    with open(SIM_RESULTS_PATH) as f:
        sim_results = json.load(f)
    with open(WORM_OUTPUT_PATH) as f:
        worm_output = json.load(f)
    return sim_results, worm_output


def fig1_scenario_comparison(sim_results):
    """Bar chart comparing success and detection rates across scenarios."""
    scenarios = ["baseline", "single_layer", "cross_layer"]
    labels = ["Baseline", "Single-Layer", "Cross-Layer"]

    success_rates = [sim_results[s]["success_rate"] * 100 for s in scenarios]
    detection_rates = [sim_results[s]["detection_rate"] * 100 for s in scenarios]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars1 = ax.bar(x - width/2, success_rates, width, label="Success Rate", color="#e74c3c")
    bars2 = ax.bar(x + width/2, detection_rates, width, label="Detection Rate", color="#3498db")

    ax.set_ylabel("Rate (%)")
    ax.set_title("Attack Success vs Detection by Defense Scenario")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.set_ylim(0, 100)

    for bar in bars1:
        ax.annotate(f'{bar.get_height():.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        ax.annotate(f'{bar.get_height():.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig1_scenario_comparison.png"), dpi=300)
    plt.close()
    print("  Saved fig1_scenario_comparison.png")


def fig2_worm_propagation(worm_output):
    """SIR-style curves showing worm spread under different policies."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)

    policies = ["baseline", "ssid_isolation", "patch_rate"]
    titles = ["Baseline", "SSID Isolation", "Faster Patching"]
    colors = {"susceptible": "#3498db", "infected": "#e74c3c", "recovered": "#2ecc71"}

    for ax, policy, title in zip(axes, policies, titles):
        data = worm_output[policy]
        t = data["t_minutes"]

        ax.plot(t, data["n_susceptible"], label="Susceptible", color=colors["susceptible"])
        ax.plot(t, data["n_infected"], label="Infected", color=colors["infected"])
        ax.plot(t, data["n_recovered"], label="Recovered", color=colors["recovered"])

        ax.set_xlabel("Time (minutes)")
        ax.set_title(f"{title}\nPeak: {data['peak_infected']} trucks @ t={data['peak_infected_t']:.0f}m")
        ax.set_xlim(0, 60)
        ax.grid(True, alpha=0.3)

        if ax == axes[0]:
            ax.set_ylabel("Number of Trucks")
            ax.legend(loc="upper right")

    plt.suptitle("H2: Worm Propagation in Truck Stop Fleet (SIR Model)", fontsize=12, y=1.02)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig2_worm_propagation.png"), dpi=300, bbox_inches="tight")
    plt.close()
    print("  Saved fig2_worm_propagation.png")


def fig3_layer_detection(sim_results):
    """Heatmap showing per-layer detection rates across scenarios."""
    scenarios = ["baseline", "single_layer", "cross_layer"]
    labels = ["Baseline", "Single-Layer", "Cross-Layer"]
    layers = ["layer_1", "layer_2", "layer_3"]
    layer_labels = ["Layer 1\n(WiFi/Physical)", "Layer 2\n(CAN Bus)", "Layer 3\n(Telematics)"]

    data = np.array([
        [sim_results[s]["layer_detection_rates"][l] * 100 for l in layers]
        for s in scenarios
    ])

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=100)

    ax.set_xticks(np.arange(len(layer_labels)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels(layer_labels)
    ax.set_yticklabels(labels)

    for i in range(len(labels)):
        for j in range(len(layer_labels)):
            text = ax.text(j, i, f"{data[i, j]:.1f}%",
                           ha="center", va="center", color="black", fontsize=11)

    ax.set_title("Detection Rate by Layer and Defense Scenario")
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Detection Rate (%)", rotation=-90, va="bottom")

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig3_layer_detection.png"), dpi=300)
    plt.close()
    print("  Saved fig3_layer_detection.png")


def fig4_path_frequencies(sim_results):
    """Stacked bar showing which attack paths are taken in each scenario."""
    scenarios = ["baseline", "single_layer", "cross_layer"]
    labels = ["Baseline", "Single-Layer", "Cross-Layer"]

    path_short = {
        "wifi_recon -> eld_firmware -> telematics_api -> cloud_backend": "Alt Path (bypass)",
        "wifi_recon -> eld_firmware -> j1939_bus -> ecu_control -> telematics_api -> cloud_backend": "Main Path (via CAN)"
    }

    main_path_freq = []
    alt_path_freq = []

    for s in scenarios:
        freqs = sim_results[s]["path_frequencies"]
        main = 0
        alt = 0
        for path, freq in freqs.items():
            if "j1939_bus" in path:
                main = freq * 100
            else:
                alt = freq * 100
        main_path_freq.append(main)
        alt_path_freq.append(alt)

    x = np.arange(len(labels))
    width = 0.5

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x, main_path_freq, width, label="Main Path (via CAN bus)", color="#9b59b6")
    ax.bar(x, alt_path_freq, width, bottom=main_path_freq, label="Alt Path (bypass)", color="#1abc9c")

    ax.set_ylabel("Path Selection (%)")
    ax.set_title("Attack Path Selection by Defense Scenario")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend(loc="upper right")
    ax.set_ylim(0, 105)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig4_path_frequencies.png"), dpi=300)
    plt.close()
    print("  Saved fig4_path_frequencies.png")


def fig5_ttc_cdf():
    """
    CDF of time-to-compromise across three scenarios.
    Requires running simulations with raw trial data.
    """
    print("  Running simulations for TTC CDF (this may take a moment)...")

    G, config = build_graph(CONFIG_PATH)
    scenarios = ["baseline", "single_layer", "cross_layer"]
    labels = ["Baseline", "Single-Layer", "Cross-Layer"]
    colors = ["#3498db", "#f39c12", "#e74c3c"]

    fig, ax = plt.subplots(figsize=(8, 5))

    for scenario, label, color in zip(scenarios, labels, colors):
        results = run_scenario(G, config, scenario, n_trials=5000)

        ttc_values = [t.time_to_compromise for t in results.raw_trials if t.success]

        if ttc_values:
            sorted_ttc = np.sort(ttc_values)
            cdf = np.arange(1, len(sorted_ttc) + 1) / len(sorted_ttc)
            ax.plot(sorted_ttc, cdf, label=f"{label} (n={len(ttc_values)})",
                    color=color, linewidth=2)

    ax.set_xlabel("Time to Compromise (minutes)")
    ax.set_ylabel("Cumulative Probability")
    ax.set_title("CDF of Time-to-Compromise by Defense Scenario")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, None)
    ax.set_ylim(0, 1)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig5_ttc_cdf.png"), dpi=300)
    plt.close()
    print("  Saved fig5_ttc_cdf.png")


def fig6_sensitivity():
    """
    Sensitivity analysis: vary Layer 3 p from 0.5 to 0.9 and show
    cross-layer advantage holds across the rangee

    This addresses the documented uncertainty in Layer 3 parameters.
    """
    print("  Running sensitivity analysis on Layer 3 p values...")

    G_base, config = build_graph(CONFIG_PATH)

    layer3_p_values = [0.50, 0.60, 0.70, 0.80, 0.90]
    scenarios = ["baseline", "single_layer", "cross_layer"]

    results_matrix = {s: [] for s in scenarios}

    for p_val in layer3_p_values:
        G_modified = G_base.copy()
        for u, v, data in G_modified.edges(data=True):
            if data["layer"] == 3:
                data["p"] = p_val

        for scenario in scenarios:
            r = run_scenario(G_modified, config, scenario, n_trials=3000)
            results_matrix[scenario].append(r.success_rate * 100)

    fig, ax = plt.subplots(figsize=(9, 5))

    colors = {"baseline": "#3498db", "single_layer": "#f39c12", "cross_layer": "#e74c3c"}
    labels = {"baseline": "Baseline", "single_layer": "Single-Layer", "cross_layer": "Cross-Layer"}
    markers = {"baseline": "o", "single_layer": "s", "cross_layer": "^"}

    for scenario in scenarios:
        ax.plot(layer3_p_values, results_matrix[scenario],
                label=labels[scenario], color=colors[scenario],
                marker=markers[scenario], linewidth=2, markersize=8)

    ax.set_xlabel("Layer 3 Transition Probability (p)")
    ax.set_ylabel("Attack Success Rate (%)")
    ax.set_title("Sensitivity Analysis: Success Rate vs Layer 3 Uncertainty\n(Layer 3 values are research gap — testing robustness)")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.45, 0.95)
    ax.set_ylim(0, 60)

    ax.axvspan(0.60, 0.75, alpha=0.15, color='gray', label='_Assumed range')
    ax.text(0.675, 55, "Assumed\nrange", ha='center', fontsize=9, color='gray')

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, "fig6_sensitivity.png"), dpi=300)
    plt.close()
    print("  Saved fig6_sensitivity.png")

    print("\n  Sensitivity Analysis Results:")
    print("  " + "-" * 60)
    print(f"  {'Layer 3 p':<12}", end="")
    for s in scenarios:
        print(f"{labels[s]:<15}", end="")
    print()
    print("  " + "-" * 60)
    for i, p_val in enumerate(layer3_p_values):
        print(f"  {p_val:<12.2f}", end="")
        for s in scenarios:
            print(f"{results_matrix[s][i]:<15.1f}", end="")
        print()
    print("  " + "-" * 60)

    return layer3_p_values, results_matrix


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading simulation data...")
    sim_results, worm_output = load_data()

    print("Generating figures...")
    fig1_scenario_comparison(sim_results)
    fig2_worm_propagation(worm_output)
    fig3_layer_detection(sim_results)
    fig4_path_frequencies(sim_results)
    fig5_ttc_cdf()
    fig6_sensitivity()

    print(f"\nAll figures saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
