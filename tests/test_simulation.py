"""
Integration tests for the simulation engine.
"""
import pytest
from src.simulation.config import SimConfig
from src.simulation.engine import run_simulation


def test_simulation_runs_without_error():
    config = SimConfig(n_blocks=10, random_seed=0)
    results = run_simulation(config)
    assert len(results) > 0


def test_all_builder_types_return_results():
    config = SimConfig(
        n_blocks=10,
        builder_types=["random", "maximal", "colluding", "inference"],
    )
    results = run_simulation(config)
    assert set(results.keys()) == {"random", "maximal", "colluding", "inference"}


def test_mev_rate_is_non_negative():
    """All builder types should have non-negative average MEV (net of gas)."""
    config = SimConfig(n_blocks=50, information_param=1.0, random_seed=1)
    results = run_simulation(config)
    for btype, result in results.items():
        assert result.mev_rate() >= 0, f"{btype} produced negative average MEV"


def test_random_builder_mev_near_zero():
    """Random builder should extract near-zero MEV (within 5% of maximal)."""
    config = SimConfig(n_blocks=100, information_param=1.0, random_seed=2,
                       builder_types=["random", "maximal"])
    results = run_simulation(config)
    rand_mev = results["random"].mev_rate()
    maxi_mev = results["maximal"].mev_rate()
    assert rand_mev < maxi_mev * 0.05 or maxi_mev == 0
