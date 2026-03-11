"""
Single-run sanity check.

Runs the simulation for 100 blocks under public mempool with all builder types.
Prints a brief summary. Use this to verify the simulation loop is working
before running the full sweep.

Expected output (after implementation):
- Random builder: ~0 MEV per block
- Maximal builder: positive MEV, rising with trade size
- Colluding builder: positive net MEV when collusion_cost is low
- Inference builder: positive MEV at alpha=0.8, near-zero at alpha=0.1
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.simulation.config import SimConfig
from src.simulation.engine import run_simulation


def main():
    config = SimConfig(
        information_param=1.0,    # public mempool
        n_blocks=100,
        random_seed=42,
        inference_accuracy=0.8,
        collusion_cost_per_tx=0.0,
    )

    print("Running baseline simulation (public mempool, 100 blocks)...")
    results = run_simulation(config)

    print("\n--- Results ---")
    for btype, result in results.items():
        print(f"{btype:12s}: mean MEV/block = {result.mev_rate():.2f}, "
              f"user harm = {result.user_harm_rate():.2f}")


if __name__ == "__main__":
    main()
