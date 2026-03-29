"""
MEV accounting and aggregate statistics.

See PLAN.md §13 for metric definitions.
"""
from dataclasses import dataclass, field
import numpy as np


@dataclass
class BlockMetrics:
    block_number: int
    builder_type: str
    information_param: float
    inference_accuracy: float

    mev_extracted: float = 0.0          # gross profit from injected txns
    sandwich_count: int = 0
    arbitrage_count: int = 0
    failed_sandwich_count: int = 0      # sandwiches where victim reverted
    gas_spent_on_mev: float = 0.0
    user_slippage_cost: float = 0.0     # welfare metric: extra slippage imposed on users
    block_value: float = 0.0            # total fees + MEV to builder
    collusion_spend: float = 0.0        # for colluding builder only

    @property
    def net_mev(self) -> float:
        return self.mev_extracted - self.gas_spent_on_mev - self.collusion_spend


@dataclass
class SimulationResults:
    config_info_param: float
    config_liquidity: int
    config_alpha: float
    builder_type: str
    config_collusion_cost: float = 0.0

    block_metrics: list[BlockMetrics] = field(default_factory=list)

    def mev_rate(self) -> float:
        """Mean MEV extracted per block."""
        return float(np.mean([m.net_mev for m in self.block_metrics]))

    def user_harm_rate(self) -> float:
        """Mean user slippage cost per block."""
        return float(np.mean([m.user_slippage_cost for m in self.block_metrics]))

    def mev_recovery_curve_point(self, baseline_mev_rate: float) -> float:
        """
        Normalized MEV: mev_rate / baseline_mev_rate (where baseline is I=1.0).
        This is the y-axis value for Figure 1 in the paper.
        """
        if baseline_mev_rate == 0:
            return 0.0
        return self.mev_rate() / baseline_mev_rate

    def to_dict(self) -> dict:
        """Serialize to flat dict for CSV output."""
        return {
            "information_param": self.config_info_param,
            "liquidity": self.config_liquidity,
            "alpha": self.config_alpha,
            "collusion_cost": self.config_collusion_cost,
            "builder_type": self.builder_type,
            "mev_rate": self.mev_rate(),
            "user_harm_rate": self.user_harm_rate(),
            "n_blocks": len(self.block_metrics),
        }
