"""
Statistical analysis of simulation results.

- OLS regression of mev_rate ~ I + L + alpha + builder_type
- Significance tests (t-tests) for MEV difference between regimes
- Breakeven collusion cost estimation
"""
import sys, os
import pandas as pd
import numpy as np
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")


def run_regression(df: pd.DataFrame):
    """
    OLS: mev_rate ~ I + log(L) + alpha + C(builder_type)

    Reports coefficients and R^2. These quantify how strongly each
    parameter drives MEV — key for the paper's Section 5 (Results).
    """
    # TODO: use statsmodels or sklearn for OLS
    raise NotImplementedError


def test_regime_difference(df: pd.DataFrame, builder_type: str = "maximal"):
    """
    Two-sample t-test: Is MEV at I=1 significantly greater than at I=0?
    For each builder type.
    """
    for btype in df["builder_type"].unique():
        public = df[(df["builder_type"] == btype) & (df["information_param"] == 1.0)]["mev_rate"]
        encrypted = df[(df["builder_type"] == btype) & (df["information_param"] == 0.0)]["mev_rate"]
        t_stat, p_val = stats.ttest_ind(public, encrypted)
        print(f"{btype}: t={t_stat:.3f}, p={p_val:.4f}")


if __name__ == "__main__":
    input_path = os.path.join(RESULTS_DIR, "sweep_results.csv")
    df = pd.read_csv(input_path)
    print("Regime difference tests:")
    test_regime_difference(df)
