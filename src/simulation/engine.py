"""
Main simulation loop.

See PLAN.md §12 for the full algorithm.
"""
import random
import numpy as np
from .config import SimConfig
from .metrics import BlockMetrics, SimulationResults
from ..amm.pool import AMMPool
from ..mempool.transaction import Transaction
from ..mempool.public import PublicMempool
from ..mempool.encrypted import EncryptedMempool
from ..mempool.partial import PartialMempool
from ..builders.random_builder import RandomBuilder
from ..builders.maximal_builder import MaximalBuilder
from ..builders.colluding_builder import ColludingBuilder
from ..builders.inference_builder import InferenceBuilder


def make_mempool(txns: list[Transaction], config: SimConfig):
    """Select mempool regime based on information_param."""
    I = config.information_param
    if I >= 1.0:
        return PublicMempool(txns)
    elif I <= 0.0:
        return EncryptedMempool(txns)
    else:
        return PartialMempool(txns, leakage_rate=I, noise_sigma=config.noise_sigma)


def generate_transactions(
    n: int,
    config: SimConfig,
    block_number: int,
    rng: random.Random,
    np_rng: np.random.Generator,
) -> list[Transaction]:
    """
    Generate n synthetic user transactions.

    Trade sizes: log-normal(μ, σ) parameterized by config.trade_size_mean/sigma
    Gas prices: Pareto(α) — fat-tailed to match empirical distributions
    Token pairs: uniform random from config.token_pairs

    See PLAN.md §12 for details.
    """
    raise NotImplementedError  # TODO


def make_builders(config: SimConfig) -> dict:
    """Instantiate one builder per type in config.builder_types."""
    builders = {}
    if "random" in config.builder_types:
        builders["random"] = RandomBuilder()
    if "maximal" in config.builder_types:
        builders["maximal"] = MaximalBuilder(information_param=config.information_param)
    if "colluding" in config.builder_types:
        builders["colluding"] = ColludingBuilder(
            collusion_cost_per_tx=config.collusion_cost_per_tx,
            budget=config.collusion_budget,
        )
    if "inference" in config.builder_types:
        builders["inference"] = InferenceBuilder(
            alpha=config.inference_accuracy,
            decision_threshold=config.decision_threshold,
        )
    return builders


def run_simulation(config: SimConfig) -> dict[str, SimulationResults]:
    """
    Run the full simulation for all builder types.
    Returns dict mapping builder_type -> SimulationResults.

    Algorithm per block:
    1. Generate transactions
    2. Wrap in configured mempool
    3. Fork AMM pool
    4. Each builder builds a block (independently, same mempool view)
    5. Measure MEV for each builder's block (hypothetical — for measurement)
    6. Advance pool state using random builder's block (neutral baseline)
    7. Record metrics

    Note: Each builder sees the same mempool and produces their block independently.
    In PBS mode, add the auction layer from pbs/block_construction.py.
    """
    rng = random.Random(config.random_seed)
    np_rng = np.random.default_rng(config.random_seed)

    pool = AMMPool(
        reserve_x=config.initial_reserves_x,
        reserve_y=config.initial_reserves_y,
        fee=config.amm_fee,
    )

    builders = make_builders(config)
    results = {
        btype: SimulationResults(
            config_info_param=config.information_param,
            config_liquidity=config.initial_reserves_x,
            config_alpha=config.inference_accuracy,
            builder_type=btype,
        )
        for btype in builders
    }

    for block_num in range(config.n_blocks):
        # Generate fresh transactions each block
        txns = generate_transactions(
            config.n_user_txns_per_block, config, block_num, rng, np_rng
        )
        mempool = make_mempool(txns, config)

        for btype, builder in builders.items():
            block = builder.build_block(mempool, pool.fork(), config.block_gas_limit)
            mev = builder.compute_mev(block, pool.fork())
            # TODO: fill in full BlockMetrics from block execution
            metrics = BlockMetrics(
                block_number=block_num,
                builder_type=btype,
                information_param=config.information_param,
                inference_accuracy=config.inference_accuracy,
                mev_extracted=mev,
            )
            results[btype].block_metrics.append(metrics)

        # Advance pool state (apply random builder's block to keep price realistic)
        # TODO: apply winning block transactions to pool
        # TODO: periodic rebalancing to prevent price drift

    return results
