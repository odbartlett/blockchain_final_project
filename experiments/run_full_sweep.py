"""
Full parameter sweep over (I, L, α).

Runs 1100 simulation configurations in parallel and saves results to
results/sweep_results.csv.

Grid:
    I_values     = [0.0, 0.1, ..., 1.0]    (11 values)
    L_values     = [100k, 500k, 1M, 5M, 10M]  (5 values)
    alpha_values = [0.0, 0.25, 0.5, 0.75, 1.0]  (5 values)
    builder_types = all 4

Total: 11 * 5 * 5 = 275 configs × 4 builders = 1100 runs.

See PLAN.md §14 for full spec.
"""
import sys
import os
import csv
import itertools
from multiprocessing import Pool, cpu_count
from dataclasses import replace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.simulation.config import SimConfig
from src.simulation.engine import run_simulation

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results")

I_VALUES = [round(i * 0.1, 1) for i in range(11)]
L_VALUES = [100_000, 500_000, 1_000_000, 5_000_000, 10_000_000]
ALPHA_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]


def run_one(args) -> list[dict]:
    I, L, alpha = args
    config = SimConfig(
        information_param=I,
        initial_reserves_x=L,
        initial_reserves_y=L,
        inference_accuracy=alpha,
        n_blocks=1_000,
    )
    results = run_simulation(config)
    return [r.to_dict() for r in results.values()]


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output_path = os.path.join(RESULTS_DIR, "sweep_results.csv")

    configs = list(itertools.product(I_VALUES, L_VALUES, ALPHA_VALUES))
    print(f"Running {len(configs)} configurations across {cpu_count()} cores...")

    all_rows = []
    with Pool(processes=cpu_count()) as pool:
        for rows in pool.imap_unordered(run_one, configs):
            all_rows.extend(rows)
            print(f"\r  Progress: {len(all_rows)} rows written", end="", flush=True)

    print(f"\nWriting {len(all_rows)} rows to {output_path}")
    if all_rows:
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_rows[0].keys())
            writer.writeheader()
            writer.writerows(all_rows)
    print("Done.")


if __name__ == "__main__":
    main()
