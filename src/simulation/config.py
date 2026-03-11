"""
Simulation configuration. All tunable parameters in one place.

See PLAN.md §11 for parameter documentation and rationale.
"""
from dataclasses import dataclass, field


@dataclass
class SimConfig:
    # --- AMM ---
    initial_reserves_x: int = 1_000_000   # base units
    initial_reserves_y: int = 1_000_000
    amm_fee: float = 0.003                # 0.3% Uniswap v2 style

    # --- Transaction generation ---
    n_user_txns_per_block: int = 50
    trade_size_mean: float = 1_000.0      # mean of log-normal (before log transform)
    trade_size_sigma: float = 1.5         # spread of log-normal
    slippage_tolerance: float = 0.01      # 1% default
    gas_price_pareto_alpha: float = 2.0   # Pareto shape for gas prices
    gas_cost_per_txn: int = 21_000        # base units (wei-equivalent)
    token_pairs: list[str] = field(
        default_factory=lambda: ["ETH/USDC", "ETH/DAI", "USDC/DAI"]
    )

    # --- Information regime ---
    information_param: float = 1.0        # I ∈ [0,1]; 1.0 = public
    noise_sigma: float = 0.3             # metadata noise std-dev (relative)

    # --- Builder parameters ---
    collusion_cost_per_tx: float = 0.0   # cost per revealed tx (colluding builder)
    collusion_budget: float = float("inf")
    inference_accuracy: float = 0.5      # α for inference builder
    decision_threshold: float = 1.2      # min E[profit]/gas_cost to act
    builder_margin: float = 0.1          # PBS auction margin

    # --- Simulation ---
    n_blocks: int = 1_000
    random_seed: int = 42
    block_gas_limit: int = 30_000_000

    # --- Builder types to run in each block ---
    # Options: "random", "maximal", "colluding", "inference", "all"
    builder_types: list[str] = field(
        default_factory=lambda: ["random", "maximal", "colluding", "inference"]
    )
