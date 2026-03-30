"""
Generate publication-quality figures from sweep_results.csv.

Figures produced (see PLAN.md §15):
  Figure 1: MEV Recovery Curve — mev_rate/mev_rate(I=1) vs I, per builder type
  Figure 2: Phase Diagram — heatmap of mev_rate(I, L) for maximal builder
  Figure 3: Collusion Breakeven — net_profit vs collusion_cost
  Figure 3 (alt): Collusion Log Scale — net_profit vs collusion_cost on log x-axis
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

BUILDER_STYLES = {
    "random": {
        "color": "gray",
        "marker": "o",
        "linestyle": "-",
    },
    "maximal": {
        "color": "red",
        "marker": "^",
        "linestyle": "-",
    },
    "colluding": {
        "color": "orange",
        "marker": "s",
        "linestyle": "-",
    },
    "inference": {
        "color": "blue",
        "marker": "D",
        "linestyle": "-",
    },
}

INFO_PARAM_STYLES = {
    0.0: {
        "color": "blue",
        "marker": "o",
        "linestyle": "-",
    },
    0.5: {
        "color": "orange",
        "marker": "s",
        "linestyle": "-",
    },
    1.0: {
        "color": "red",
        "marker": "^",
        "linestyle": "-",
    },
}

ALPHA_BY_I = {
    0.0: 0.9,   # blue
    0.5: 1.0,  # orange -> fully visible
    1.0: 0.45,   # red -> transparent
}

LINEWIDTH = 2
MARKERSIZE = 6
ALPHA = 0.75
MARKEREDGEWIDTH = 0.7
MARKEREDGECOLOR = "white"


def load_data() -> pd.DataFrame:
    return pd.read_csv(INPUT_PATH)


def _plot_series(ax, x, y, label: str, style: dict, alpha: float = ALPHA):
    ax.plot(
        x,
        y,
        label=label,
        color=style["color"],
        marker=style["marker"],
        linestyle=style["linestyle"],
        linewidth=LINEWIDTH,
        markersize=MARKERSIZE,
        alpha=alpha,
        markeredgecolor=MARKEREDGECOLOR,
        markeredgewidth=MARKEREDGEWIDTH,
    )


def figure1_mev_recovery_curve(df: pd.DataFrame):
    """MEV recovery curve: normalized MEV vs I, per builder type."""
    fig, ax = plt.subplots(figsize=(7, 5))

    df = df[df["collusion_cost"] == 0].copy()
    baseline = df[df["information_param"] == 1.0].groupby("builder_type")["mev_rate"].mean()

    all_y = []
    for btype, style in BUILDER_STYLES.items():
        subset = (
            df[df["builder_type"] == btype]
            .groupby("information_param")["mev_rate"]
            .mean()
            .sort_index()
        )
        if subset.empty:
            continue
        norm = baseline.get(btype, 1.0)
        y = subset.values / max(norm, 1e-9)
        all_y.extend(y.tolist())
        _plot_series(ax, subset.index, y, btype, style)

    ax.set_xlabel("Information Parameter I")
    ax.set_ylabel("Normalized MEV (fraction of I=1 baseline)")
    ax.set_title("Figure 1: MEV Recovery Curve by Builder Type")
    ax.legend()
    ax.set_xlim(0, 1)

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
    sns.heatmap(
        subset,
        ax=ax,
        cmap="YlOrRd",
        annot=False,
        fmt=".0f",
        xticklabels=[f"{v/1e6:.1f}M" for v in subset.columns],
        cbar_kws={"label": "Mean MEV per block"},
    )
    ax.set_xlabel("Liquidity L (reserves)")
    ax.set_ylabel("Information Parameter I")
    ax.set_title("Figure 2: MEV Phase Diagram (Maximal Builder)")
    plt.tight_layout()
    return fig


def _get_collusion_series(df: pd.DataFrame):
    subset = df[df["builder_type"] == "colluding"].copy()
    if subset.empty:
        return None

    series = {}
    for I, style in INFO_PARAM_STYLES.items():
        grp = (
            subset[abs(subset["information_param"] - I) < 1e-9]
            .groupby("collusion_cost")["mev_rate"]
            .mean()
            .sort_index()
        )
        if not grp.empty:
            series[I] = (grp, style)

    return series if series else None


def figure3_collusion_breakeven(df: pd.DataFrame):
    """Figure 3: Net MEV vs collusion cost in the breakeven region."""
    series = _get_collusion_series(df)
    if series is None:
        print("  [figure3_collusion_breakeven] No colluding builder rows — skipping.")
        return None

    fig, ax = plt.subplots(figsize=(6.5, 5))

    all_vals = [v for grp, _ in series.values() for v in grp.values]
    y_max = max(all_vals) if all_vals else 1000

    for I in [0.0, 0.5, 1.0]:
        if I not in series:
            continue
        grp, style = series[I]
        ax.plot(
            grp.index,
            grp.values,
            label=f"I = {I}",
            color=style["color"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            linewidth=2,
            markersize=6,
            alpha=ALPHA_BY_I[I],
            markeredgecolor="white",
            markeredgewidth=0.7,
        )

    ax.axhline(0, linestyle="--", color="black", alpha=0.5, linewidth=1)
    ax.set_xlim(-0.5, 25)
    ax.set_ylim(-y_max * 0.05, y_max * 1.12)
    ax.set_xlabel("Collusion Cost per Transaction c")
    ax.set_ylabel("Mean Net MEV per block")
    ax.set_title("Figure 3: Collusion Breakeven Cost")
    ax.legend(title="Info param I")

    plt.tight_layout()
    return fig


def figure3_collusion_log_scale(df: pd.DataFrame):
    """Figure 3 (alt): Net MEV vs collusion cost over full range on log x-axis."""
    series = _get_collusion_series(df)
    if series is None:
        print("  [figure3_collusion_log_scale] No colluding builder rows — skipping.")
        return None

    fig, ax = plt.subplots(figsize=(6.5, 5))

    all_vals = [v for grp, _ in series.values() for v in grp.values]
    y_max = max(all_vals) if all_vals else 1000

    for I in [0.0, 0.5, 1.0]:
        if I not in series:
            continue
        grp, style = series[I]
        nonzero = grp[grp.index > 0]
        if nonzero.empty:
            continue
        ax.plot(
            nonzero.index,
            nonzero.values,
            label=f"I = {I}",
            color=style["color"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            linewidth=2,
            markersize=6,
            alpha=ALPHA_BY_I[I],
            markeredgecolor="white",
            markeredgewidth=0.7,
        )

    ax.axhline(0, linestyle="--", color="black", alpha=0.5, linewidth=1)
    ax.set_xscale("log")
    ax.set_xlim(0.8, 3000)
    ax.set_ylim(-y_max * 0.05, y_max * 1.12)
    ax.set_xlabel("Collusion Cost per Transaction c (log scale)")
    ax.set_ylabel("Mean Net MEV per block")
    ax.set_title("Figure 3: Collusion Cost (Log Scale)")
    ax.legend(title="Info param I")

    plt.tight_layout()
    return fig


def figure4_mev_vs_alpha(df: pd.DataFrame):
    """MEV vs inference accuracy α at I=0 (encrypted mempool)."""
    subset = df[
        (df["information_param"] == 0.0) & (df["builder_type"] == "inference")
    ].groupby("alpha")["mev_rate"].mean().sort_index()

    fig, ax = plt.subplots(figsize=(6, 4))
    _plot_series(ax, subset.index, subset.values, "inference", BUILDER_STYLES["inference"])
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

    fig3a = figure3_collusion_breakeven(df)
    if fig3a is not None:
        _save(fig3a, "figure3_collusion_breakeven")

    fig3b = figure3_collusion_log_scale(df)
    if fig3b is not None:
        _save(fig3b, "figure3_collusion_log_scale")

    _save(figure4_mev_vs_alpha(df), "figure4_mev_vs_alpha")


if __name__ == "__main__":
    main()