"""
Fast parameter sweep to generate data for all four paper figures.

Uses n_blocks=100 per run (vs 1000 in run_full_sweep.py) for speed.

Sweep design:
  Figure 1 data  — I in [0..1] (11 pts), all 4 builders, L=1M, α=0.8
  Figure 2 data  — I × L grid (11 × 5), maximal builder only
  Figure 3 data  — collusion_cost sweep (12 pts), I ∈ {0.0, 0.5, 1.0}, colluding builder
  Figure 4 data  — α sweep (11 pts), I=0.0, inference builder only

All results appended to results/sweep_results.csv.
"""
import sys
import os
import csv
import itertools
import multiprocessing
from dataclasses import asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.simulation.config import SimConfig
from src.simulation.engine import run_simulation

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")
OUT_CSV = os.path.join(RESULTS_DIR, "sweep_results.csv")

N_BLOCKS = 100   # fast; use 1000 for publication quality


# ---------------------------------------------------------------------------
# Sweep parameter sets
# ---------------------------------------------------------------------------

I_GRID = [round(v * 0.1, 1) for v in range(11)]          # 0.0 … 1.0
L_GRID = [250_000, 500_000, 1_000_000, 2_000_000, 4_000_000]
ALPHA_GRID = [round(v * 0.1, 1) for v in range(11)]       # 0.0 … 1.0
COLLUSION_COSTS = [0, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]


def _run(cfg_dict: dict) -> list[dict]:
    """Run one SimConfig and return list of per-builder row dicts."""
    config = SimConfig(**cfg_dict)
    results = run_simulation(config)
    rows = []
    for btype, res in results.items():
        row = res.to_dict()
        rows.append(row)
    return rows


def _build_configs() -> list[dict]:
    """Enumerate all parameter combinations to sweep."""
    configs = []

    # ------------------------------------------------------------------
    # Figure 1 + 4 base: all builders, vary I, fixed L and α
    # (α=0.8 gives inference builder meaningful signal)
    # ------------------------------------------------------------------
    for I in I_GRID:
        configs.append(dict(
            information_param=I,
            initial_reserves_x=1_000_000,
            initial_reserves_y=1_000_000,
            inference_accuracy=0.8,
            collusion_cost_per_tx=0.0,
            collusion_budget=float("inf"),
            n_blocks=N_BLOCKS,
            builder_types=["random", "maximal", "colluding", "inference"],
        ))

    # ------------------------------------------------------------------
    # Figure 2: I × L grid, maximal builder only (fast)
    # ------------------------------------------------------------------
    for I, L in itertools.product(I_GRID, L_GRID):
        if L == 1_000_000:
            continue  # already covered above
        configs.append(dict(
            information_param=I,
            initial_reserves_x=L,
            initial_reserves_y=L,
            inference_accuracy=0.8,
            collusion_cost_per_tx=0.0,
            collusion_budget=float("inf"),
            n_blocks=N_BLOCKS,
            builder_types=["maximal"],
        ))

    # ------------------------------------------------------------------
    # Figure 3: collusion cost breakeven, vary cost at three I values
    # ------------------------------------------------------------------
    for cost, I in itertools.product(COLLUSION_COSTS, [0.0, 0.5, 1.0]):
        configs.append(dict(
            information_param=I,
            initial_reserves_x=1_000_000,
            initial_reserves_y=1_000_000,
            inference_accuracy=0.8,
            collusion_cost_per_tx=float(cost),
            collusion_budget=float("inf"),
            n_blocks=N_BLOCKS,
            builder_types=["colluding"],
        ))

    # ------------------------------------------------------------------
    # Figure 4: α sweep at I=0 (encrypted mempool)
    # ------------------------------------------------------------------
    for alpha in ALPHA_GRID:
        if alpha == 0.8:
            continue  # already covered above (I=0 row)
        configs.append(dict(
            information_param=0.0,
            initial_reserves_x=1_000_000,
            initial_reserves_y=1_000_000,
            inference_accuracy=alpha,
            collusion_cost_per_tx=0.0,
            collusion_budget=float("inf"),
            n_blocks=N_BLOCKS,
            builder_types=["inference"],
        ))

    return configs


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    configs = _build_configs()
    print(f"Running {len(configs)} configurations × {N_BLOCKS} blocks each…")

    # Parallel execution using all available CPUs
    n_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"Using {n_workers} worker processes")

    all_rows: list[dict] = []
    completed = 0

    with multiprocessing.Pool(n_workers) as pool:
        for rows in pool.imap_unordered(_run, configs, chunksize=4):
            all_rows.extend(rows)
            completed += 1
            if completed % 20 == 0 or completed == len(configs):
                print(f"  {completed}/{len(configs)} done ({len(all_rows)} rows so far)")

    # Write CSV
    if not all_rows:
        print("No results — check for errors above.")
        return

    fieldnames = list(all_rows[0].keys())
    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nSaved {len(all_rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
