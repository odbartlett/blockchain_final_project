"""
Unit tests for builder adversaries.

Key invariants:
- Random builder extracts near-zero MEV (no injected txns)
- Maximal builder at I=1 extracts more MEV than random builder
- Inference builder at I=0 extracts less MEV than maximal builder at I=1
- Colluding builder net profit decreases as collusion_cost increases
"""
import pytest
from src.amm.pool import AMMPool
from src.simulation.config import SimConfig
from src.simulation.engine import generate_transactions, make_mempool
from src.builders.random_builder import RandomBuilder
from src.builders.maximal_builder import MaximalBuilder
from src.builders.colluding_builder import ColludingBuilder
from src.builders.inference_builder import InferenceBuilder
import random, numpy as np


def make_test_env(I=1.0, n_txns=20):
    config = SimConfig(information_param=I, n_user_txns_per_block=n_txns, n_blocks=1)
    pool = AMMPool(1_000_000, 1_000_000, fee=0.003)
    rng = random.Random(0)
    np_rng = np.random.default_rng(0)
    txns = generate_transactions(n_txns, config, block_number=0, rng=rng, np_rng=np_rng)
    mempool = make_mempool(txns, config)
    return pool, mempool, config


def test_random_builder_no_injected_txns():
    pool, mempool, config = make_test_env(I=1.0)
    builder = RandomBuilder()
    block = builder.build_block(mempool, pool, config.block_gas_limit)
    # No transaction should have sender == "BUILDER"
    assert all(getattr(t, "sender", None) != "BUILDER" for t in block)


def test_maximal_builder_extracts_more_than_random():
    pool, mempool, config = make_test_env(I=1.0)
    rand = RandomBuilder()
    maxi = MaximalBuilder(information_param=1.0)
    rand_block = rand.build_block(mempool, pool, config.block_gas_limit)
    maxi_block = maxi.build_block(mempool, pool, config.block_gas_limit)
    rand_mev = rand.compute_mev(rand_block, pool.fork())
    maxi_mev = maxi.compute_mev(maxi_block, pool.fork())
    assert maxi_mev >= rand_mev


def test_maximal_builder_mev_drops_at_zero_info():
    pool_pub, mempool_pub, config_pub = make_test_env(I=1.0)
    pool_enc, mempool_enc, config_enc = make_test_env(I=0.0)
    maxi_pub = MaximalBuilder(information_param=1.0)
    maxi_enc = MaximalBuilder(information_param=0.0)
    block_pub = maxi_pub.build_block(mempool_pub, pool_pub, config_pub.block_gas_limit)
    block_enc = maxi_enc.build_block(mempool_enc, pool_enc, config_enc.block_gas_limit)
    mev_pub = maxi_pub.compute_mev(block_pub, pool_pub.fork())
    mev_enc = maxi_enc.compute_mev(block_enc, pool_enc.fork())
    # MEV at I=0 should be substantially less than at I=1
    assert mev_enc < mev_pub * 0.1  # less than 10% of public MEV


def test_colluding_builder_net_profit_decreases_with_cost():
    results = []
    for cost in [0.0, 10.0, 100.0, 1000.0]:
        pool, mempool, config = make_test_env(I=0.0)
        builder = ColludingBuilder(collusion_cost_per_tx=cost, budget=float("inf"))
        block = builder.build_block(mempool, pool, config.block_gas_limit)
        results.append(builder.last_net_profit)
    # Net profit should be monotonically non-increasing in cost
    for i in range(len(results) - 1):
        assert results[i] >= results[i + 1]
