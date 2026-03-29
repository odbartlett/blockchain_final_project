"""
Generate publication-quality figures from sweep_results.csv.

Figures produced (see PLAN.md §15):
  Figure 1: MEV Recovery Curve — mev_rate/mev_rate(I=1) vs I, per builder type
  Figure 2: Phase Diagram — heatmap of mev_rate(I, L) for maximal builder
  Figure 3: Collusion Breakeven — net_profit vs collusion_cost (requires re-run)
  Figure 4: MEV vs Inference Accuracy α at I=0

Run after run_full_sweep.py.
"""
import sys
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
INPUT_PATH = os.path.join(RESULTS_DIR, "sweep_results.csv")
FIG_DIR = os.path.join(RESULTS_DIR, "figures")

BUILDER_COLORS = {
    "random": "gray",
    "maximal": "red",
    "colluding": "orange",
    "inference": "blue",
}


def load_data() -> pd.DataFrame:
    return pd.read_csv(INPUT_PATH)


def figure1_mev_recovery_curve(df: pd.DataFrame):
    """MEV recovery curve: normalized MEV vs I, per builder type."""
    fig, ax = plt.subplots(figsize=(7, 5))

    # Normalize by I=1.0 value per builder type
    baseline = df[df["information_param"] == 1.0].groupby("builder_type")["mev_rate"].mean()

    all_y = []
    for btype, color in BUILDER_COLORS.items():
        subset = df[df["builder_type"] == btype].groupby("information_param")["mev_rate"].mean()
        norm = baseline.get(btype, 1.0)
        y = subset.values / max(norm, 1e-9)
        all_y.extend(y.tolist())
        ax.plot(subset.index, y, label=btype, color=color, marker="o", markersize=4)

    ax.set_xlabel("Information Parameter I")
    ax.set_ylabel("Normalized MEV (fraction of I=1 baseline)")
    ax.set_title("Figure 1: MEV Recovery Curve by Builder Type")
    ax.legend()
    ax.set_xlim(0, 1)

    # Auto-scale y to show all lines including values > 1 and negatives
    y_min = min(all_y) if all_y else 0
    y_max = max(all_y) if all_y else 1
    pad = (y_max - y_min) * 0.1 or 0.1
    ax.set_ylim(y_min - pad, y_max + pad)

    ax.axhline(0.0, linestyle="-", color="black", alpha=0.2, linewidth=0.8)
    ax.axhline(1.0, linestyle="--", color="black", alpha=0.4, linewidth=1, label="I=1 baseline")
    plt.tight_layout()
    return fig


def figure2_phase_diagram(df: pd.DataFrame):
    """Phase diagram: heatmap of mev_rate over (I, L) for maximal builder."""
    subset = df[df["builder_type"] == "maximal"].groupby(
        ["information_param", "liquidity"]
    )["mev_rate"].mean().unstack("liquidity")

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(subset, ax=ax, cmap="YlOrRd", annot=False, fmt=".0f",
                xticklabels=[f"{v/1e6:.1f}M" for v in subset.columns],
                cbar_kws={"label": "Mean MEV per block"})
    ax.set_xlabel("Liquidity L (reserves)")
    ax.set_ylabel("Information Parameter I")
    ax.set_title("Figure 2: MEV Phase Diagram (Maximal Builder)")
    plt.tight_layout()
    return fig


def figure3_collusion_breakeven(df: pd.DataFrame):
    """Net MEV vs collusion cost at I ∈ {0.0, 0.5, 1.0} for the colluding builder."""
    subset = df[df["builder_type"] == "colluding"].copy()
    if subset.empty:
        print("  [figure3] No colluding builder rows — skipping.")
        return None

    fig, ax = plt.subplots(figsize=(7, 5))
    i_colors = {0.0: "blue", 0.5: "orange", 1.0: "red"}

    for I, color in i_colors.items():
        grp = subset[subset["information_param"] == I].groupby("collusion_cost")["mev_rate"].mean()
        if grp.empty:
            continue
        ax.plot(grp.index, grp.values, marker="o", markersize=4, color=color, label=f"I = {I}")

    ax.axhline(0, linestyle="--", color="black", alpha=0.4, linewidth=1)
    ax.set_xlabel("Collusion Cost per Transaction c")
    ax.set_ylabel("Mean Net MEV per block")
    ax.set_title("Figure 3: Collusion Breakeven Cost")
    ax.legend(title="Info param I")
    plt.tight_layout()
    return fig


def figure4_mev_vs_alpha(df: pd.DataFrame):
    """MEV vs inference accuracy α at I=0 (encrypted mempool)."""
    subset = df[
        (df["information_param"] == 0.0) & (df["builder_type"] == "inference")
    ].groupby("alpha")["mev_rate"].mean()

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(subset.index, subset.values, marker="o", color="blue")
    ax.set_xlabel("Inference Accuracy α")
    ax.set_ylabel("Mean MEV per block")
    ax.set_title("Figure 4: MEV Recovery from Metadata Inference (I=0)")
    ax.set_xlim(0, 1)
    plt.tight_layout()
    return fig


def _save(fig, stem: str):
    """Save figure as both PDF and PNG."""
    for ext in ("pdf", "png"):
        path = os.path.join(FIG_DIR, f"{stem}.{ext}")
        fig.savefig(path, bbox_inches="tight", dpi=150)
        print(f"Saved {path}")


def main():
    os.makedirs(FIG_DIR, exist_ok=True)
    print(f"Loading data from {INPUT_PATH}...")
    df = load_data()

    _save(figure1_mev_recovery_curve(df), "figure1_mev_recovery_curve")
    _save(figure2_phase_diagram(df), "figure2_phase_diagram")
    fig3 = figure3_collusion_breakeven(df)
    if fig3 is not None:
        _save(fig3, "figure3_collusion_breakeven")
    _save(figure4_mev_vs_alpha(df), "figure4_mev_vs_alpha")


if __name__ == "__main__":
    main()
