"""
Supplemental MEV analysis plots.
Produces per-builder MEV breakdown and variance analysis.
"""
import sys, os
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def plot_mev_by_builder(df: pd.DataFrame):
    """Side-by-side MEV rate at I=0, 0.5, 1.0 for all builder types."""
    fig, axes = plt.subplots(1, 3, figsize=(14, 4), sharey=True)
    for ax, I in zip(axes, [0.0, 0.5, 1.0]):
        sub = df[df["information_param"] == I].groupby("builder_type")["mev_rate"].mean()
        sub.plot(kind="bar", ax=ax, color=["gray", "red", "orange", "blue"])
        ax.set_title(f"I = {I}")
        ax.set_xlabel("")
        ax.set_ylabel("Mean MEV/block" if I == 0.0 else "")
        ax.tick_params(axis="x", rotation=30)
    fig.suptitle("MEV by Builder Type at Fixed Information Levels")
    plt.tight_layout()
    return fig


if __name__ == "__main__":
    input_path = os.path.join(RESULTS_DIR, "sweep_results.csv")
    df = pd.read_csv(input_path)
    fig = plot_mev_by_builder(df)
    out = os.path.join(RESULTS_DIR, "figures", "mev_by_builder.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, bbox_inches="tight")
    print(f"Saved {out}")
