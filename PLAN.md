# PLAN.md — MEV Under Partial Mempool Privacy

**Project:** Modeling MEV Under Partial Mempool Privacy: Adversarial Builders in Public vs. Threshold-Encrypted Regimes
**Team:** Owen Bartlett, Jacob Gutsin

---

## Overview

This document is the canonical implementation guide. All code should be built to produce reproducible, quantitative results that answer the three primary research questions:

1. Under what information conditions does sandwich/arbitrage MEV remain profitable?
2. How much MEV can be recovered via Bayesian inference from metadata alone?
3. Do threshold-encrypted mempools eliminate harmful MEV, or shift it to inference strategies?
4. How do adversary types change equilibrium outcomes?

The output is a set of **phase diagrams** and **MEV recovery curves** over the information parameter `I ∈ [0,1]`, parameterized by liquidity `L`, trade size distribution `D`, and inference accuracy `α`.

---

## Repository Structure

```
blockchain_final_project/
├── PLAN.md                        ← This file
├── README.md
├── requirements.txt
├── src/
│   ├── amm/
│   │   └── pool.py                ← Constant-product AMM (x·y = k)
│   ├── mempool/
│   │   ├── transaction.py         ← Transaction + metadata dataclasses
│   │   ├── public.py              ← Full-visibility mempool
│   │   ├── encrypted.py           ← Threshold-encrypted mempool
│   │   └── partial.py             ← Metadata-leaking partial mempool
│   ├── builders/
│   │   ├── base.py                ← Abstract Builder interface
│   │   ├── random_builder.py      ← Baseline: random ordering
│   │   ├── maximal_builder.py     ← Upper bound: full MEV extraction
│   │   ├── colluding_builder.py   ← Cost-adjusted collusion model
│   │   └── inference_builder.py   ← Bayesian probabilistic strategist
│   ├── pbs/
│   │   └── block_construction.py  ← PBS-style slot auction + block assembly
│   ├── mev/
│   │   ├── sandwich.py            ← Sandwich attack detector + executor
│   │   ├── arbitrage.py           ← Cross-pool arbitrage detector
│   │   └── liquidation.py         ← Undercollateralized position liquidation
│   └── simulation/
│       ├── engine.py              ← Main simulation loop
│       ├── config.py              ← All tunable parameters
│       └── metrics.py             ← MEV accounting + phase measurements
├── experiments/
│   ├── run_baseline.py            ← Single-run sanity check
│   ├── run_full_sweep.py          ← Parameter sweep over (I, L, D, α)
│   └── phase_diagrams.py          ← Generates publication-quality figures
├── analysis/
│   ├── plot_mev_curves.py         ← MEV recovery curves per adversary
│   └── statistical_analysis.py    ← Regression, significance tests
├── tests/
│   ├── test_amm.py
│   ├── test_builders.py
│   └── test_simulation.py
└── results/                       ← Auto-created by experiments; gitignored
    └── .gitkeep
```

---

## Module-by-Module Build Plan

### 1. `src/amm/pool.py` — AMM Pricing Engine

**Purpose:** Provide a deterministic, closed-form pricing oracle so MEV values are mathematically precise.

**What to implement:**
- `AMMPool` class with reserves `(x, y)`, fee `f ∈ [0,1)`
- `get_price() -> float` — spot price `y/x`
- `swap(token_in, amount_in) -> amount_out` — constant-product formula with fee deduction:
  ```
  amount_out = (amount_in * (1-f) * y) / (x + amount_in * (1-f))
  ```
- `price_impact(amount_in) -> float` — fractional price shift after swap
- `sandwich_profit(victim_amount, front_amount) -> float` — closed-form sandwich P&L given front-run size and victim size; this is the key MEV primitive

**Key design notes:**
- All values should be in integer units (satoshis / wei-equivalents) to avoid float rounding errors. Use Python's `Decimal` or integer arithmetic where precision matters.
- The pool should be **stateless between transactions by default** (cloned per block) so order-dependence is explicit.
- Expose a `fork()` method that deep-copies pool state — builders will speculatively simulate swaps without committing.

**Validation:** Unit-test that `swap(swap_inverse(x)) ≈ x` and that sandwich profit is zero when `front_amount = 0`.

---

### 2. `src/mempool/transaction.py` — Transaction Data Model

**Purpose:** Unify the transaction representation across all three information regimes.

**Dataclass fields:**
```python
@dataclass
class Transaction:
    tx_id: str            # UUID
    sender: str           # address (opaque string)
    token_in: str         # "ETH", "USDC", etc.
    token_out: str
    amount_in: int        # in base units
    min_amount_out: int   # slippage tolerance → encodes trade aggressiveness
    gas_price: int        # priority fee
    deadline: int         # block number

    # Metadata fields (always visible even in encrypted regime)
    metadata_gas_price: int       # copy of gas_price (public)
    metadata_size_bucket: str     # "small"/"medium"/"large" (binned, not exact)
    metadata_token_pair: str      # "ETH/USDC" (always public)
    metadata_deadline_urgency: float  # normalized time-to-deadline

    # Visibility flags (set by mempool regime)
    payload_visible: bool = True  # False in encrypted regime
```

**Key design notes:**
- `metadata_size_bucket` encodes the *noisy* information available in encrypted mempools — exact amounts are hidden, but the gas price and rough order of magnitude leak.
- `min_amount_out` is crucial: it sets the range within which a sandwich can be inserted without reverting the victim's transaction.

---

### 3. `src/mempool/public.py`, `encrypted.py`, `partial.py` — Mempool Regimes

**Purpose:** Wrap a list of pending transactions and expose only the information appropriate to each regime.

**`PublicMempool`:**
- Returns all `Transaction` objects with `payload_visible=True`
- No filtering, no noise

**`EncryptedMempool`:**
- Returns transactions with `payload_visible=False`
- `amount_in`, `min_amount_out`, `sender` are set to `None` or sentinel values
- Metadata fields (`gas_price`, `size_bucket`, `token_pair`, `deadline_urgency`) remain accessible
- Represents threshold-encryption where payload is committed but not yet decryptable

**`PartialMempool(leakage_rate: float, noise_sigma: float)`:**
- With probability `leakage_rate`, reveals exact `amount_in` (models partial decryption / side-channel)
- Otherwise, returns only metadata + Gaussian-noised amount estimate: `amount_in_noisy ~ N(true_amount, noise_sigma * true_amount)`
- `leakage_rate` is the primary lever for the information parameter `I`

**Relationship between `I` and mempool parameters:**
```
I = 0.0  → EncryptedMempool (no leakage, metadata only)
I = 1.0  → PublicMempool (full payload)
I ∈ (0,1) → PartialMempool(leakage_rate=I, noise_sigma=f(I))
```
Formally: `I` is the mutual information fraction between the builder's observation and the true transaction content, normalized to [0,1]. In the simulation we approximate this as `leakage_rate` since it directly determines how many transactions are fully visible.

---

### 4. `src/builders/base.py` — Abstract Builder

**Purpose:** Define the interface all builders must implement.

```python
class Builder(ABC):
    def __init__(self, information_param: float): ...

    @abstractmethod
    def build_block(
        self,
        mempool: BaseMempool,
        pool: AMMPool,
        block_gas_limit: int,
    ) -> list[Transaction]:
        """Return an ordered list of transactions (the proposed block)."""
        ...

    def compute_mev(self, block: list[Transaction], pool: AMMPool) -> float:
        """Execute the block sequentially against a pool fork; return total builder profit."""
        ...
```

**Key design note:** `compute_mev` must simulate executing each transaction in order against a pool fork and track the balance delta of the builder's own injected transactions (front-run and back-run legs). This is the ground-truth MEV measurement.

---

### 5. `src/builders/random_builder.py` — Baseline

**Purpose:** Establish a zero-MEV baseline. Orders valid transactions randomly (respects gas limit, drops invalid txns).

**Implementation:**
- Shuffle the visible mempool randomly
- Pack greedily by gas limit
- **No injected transactions** — measures "accidental" MEV from lucky orderings

**Expected result:** MEV ≈ 0 on average, with small variance. This calibrates the simulation — if the baseline extracts significant MEV, there is a bug in the MEV accounting.

---

### 6. `src/builders/maximal_builder.py` — Maximal Extractor

**Purpose:** Compute the theoretical upper bound on MEV under each regime. This is the most complex builder.

**Algorithm (public mempool case):**
1. For each user swap transaction `t` in the mempool:
   a. Compute the optimal front-run size `f*` that maximizes sandwich profit: `argmax_f sandwich_profit(pool, f, t.amount_in)`
   b. Analytically: `f* = sqrt(x * t.amount_in) - x` (closed form for constant-product AMM)
   c. Record the (front_run, victim, back_run) triple and its profit
2. Find the subset of sandwich opportunities that fit within the block gas limit without conflicting
3. Fill remaining gas with highest-fee non-MEV transactions
4. Return the block

**Algorithm (encrypted mempool case, I=0):**
- No profitable sandwiches possible because `amount_in` is hidden and `min_amount_out` is unknown
- Builder falls back to fee-maximizing order
- MEV should collapse to near zero

**Algorithm (partial case, I ∈ (0,1)):**
- For transactions where `payload_visible=True`: apply full sandwich logic
- For metadata-only transactions: skip sandwich (or pass to inference builder logic)

**Key formula to implement:**
```
optimal_front_run(x, y, v) = sqrt(x * (x + v)) - x
sandwich_profit(x, y, f, v) = amm_out(pool_after_front(f), v) - v_original_out - gas_cost
```
where `v` is victim swap size and `x,y` are pool reserves.

---

### 7. `src/builders/colluding_builder.py` — Colluding Builder

**Purpose:** Model incentive failures — a builder that pays a cost `c` to expand its information set.

**Parameters:**
- `collusion_cost_per_tx: float` — cost paid to a corrupt decryptor per transaction revealed
- `budget: float` — total information budget per block

**Algorithm:**
1. Start with encrypted mempool (metadata only)
2. For each pending transaction, estimate expected sandwich profit from metadata alone (use inference model)
3. If `expected_profit > collusion_cost_per_tx`, purchase the decryption and execute full sandwich
4. Otherwise, skip
5. Measure net profit: `total_sandwich_profit - total_collusion_cost`

**Key research insight this models:** This builder answers "at what encryption cost does the threshold scheme become economically secure?" Plot `net_profit(c)` — the zero-crossing gives the minimum cost that deters collusion.

---

### 8. `src/builders/inference_builder.py` — Inference-Based Builder

**Purpose:** Purely metadata-based probabilistic strategist. No collusion — only observes what is public.

**Algorithm:**
1. For each encrypted transaction `t` (metadata only):
   a. Estimate `P(amount_in | size_bucket, gas_price, token_pair, deadline_urgency)` using a prior distribution (calibrated from historical data or synthetic training set)
   b. Compute `E[sandwich_profit | metadata]` by integrating over the prior
   c. If `E[profit] > threshold * gas_cost`, inject a speculative sandwich
2. Parameter `α` (inference accuracy) is the correlation between `estimated_amount` and `true_amount`:
   - `α = 1.0`: perfect inference (equivalent to public mempool for MEV purposes)
   - `α = 0.0`: random guessing (builder loses money on failed sandwiches due to gas costs)

**Implementation of the prior:**
- Fit a log-normal distribution `LogNormal(μ, σ)` to a training set of synthetic transactions
- Condition on `size_bucket` to get three conditional distributions (small/medium/large)
- Use `gas_price` as a secondary signal (high-fee txns tend to be larger)
- α is the Pearson correlation between estimated and true amounts; tune `σ` to achieve target α

**Key research insight:** Plot `MEV(α)` — this is the "MEV recovery curve" showing how quickly MEV rebounds as inference improves. The slope of this curve is a key result of the paper.

---

### 9. `src/mev/sandwich.py`, `arbitrage.py`, `liquidation.py` — MEV Primitives

**`sandwich.py`:**
- `find_sandwich_opportunities(txns, pool) -> list[SandwichOp]`
- `execute_sandwich(pool_fork, front_size, victim_txn) -> (profit, new_pool_state)`
- Sandwich is only valid if victim's `min_amount_out` is satisfied after the front-run

**`arbitrage.py`:**
- `find_arbitrage(pool_a, pool_b, token_path) -> list[ArbOp]`
- Two-pool circular arbitrage: buy on cheaper pool, sell on expensive
- Optimal size: `sqrt(x_a * x_b) - x_a` (harmonic mean of reserves)

**`liquidation.py`:**
- `find_liquidations(positions, pool) -> list[LiquidationOp]`
- A position becomes liquidatable when `collateral_value < debt * liquidation_threshold`
- Builder triggers liquidation by moving pool price past the threshold

**Note:** For a minimal first version, focus on **sandwich only** — it is the most common and most analytically tractable MEV type. Add arbitrage and liquidation in phase 2.

---

### 10. `src/pbs/block_construction.py` — PBS Block Auction

**Purpose:** Simulate the Proposer-Builder Separation auction where multiple builders bid for the block slot.

**Mechanism:**
1. Each builder receives the same mempool view (for their regime)
2. Each builder constructs a candidate block and computes a bid equal to their expected profit minus a margin
3. The highest-bidding builder wins the slot
4. Track: who wins, what MEV was extracted, how much was paid to the proposer

**Key parameters:**
- `num_builders: int` — competition level (more builders → less MEV per builder, more efficient market)
- `builder_types: list[str]` — mix of adversary types competing in the same auction

**Research question this enables:** Does the presence of inference-based builders in a threshold-encrypted mempool force fee escalation similar to PGAs in public mempools?

---

### 11. `src/simulation/config.py` — Parameter Space

Define all experimental parameters in one place:

```python
@dataclass
class SimConfig:
    # AMM
    initial_reserves_x: int = 1_000_000
    initial_reserves_y: int = 1_000_000
    amm_fee: float = 0.003           # 0.3% Uniswap-style fee

    # Transaction generation
    n_user_txns_per_block: int = 50
    trade_size_mean: float = 1000.0  # mean of LogNormal trade size
    trade_size_sigma: float = 1.5    # spread of trade sizes
    slippage_tolerance: float = 0.01 # 1% default slippage

    # Information regime
    information_param: float = 1.0   # I ∈ [0,1]; 1.0 = public
    noise_sigma: float = 0.3         # metadata noise level

    # Builder parameters
    collusion_cost: float = 0.0      # cost per revealed tx (colluding builder)
    inference_accuracy: float = 0.5  # α for inference builder
    decision_threshold: float = 1.2  # min E[profit]/gas_cost ratio to act

    # Simulation
    n_blocks: int = 1000
    random_seed: int = 42
    block_gas_limit: int = 30_000_000
```

---

### 12. `src/simulation/engine.py` — Simulation Loop

**Algorithm for one simulation run:**

```
for block_number in range(n_blocks):
    1. Generate n_user_txns_per_block transactions (log-normal sizes, uniform token pairs)
    2. Wrap in the configured mempool regime (public / encrypted / partial)
    3. Fork the AMM pool state
    4. Each builder receives the mempool view and builds a candidate block
    5. PBS auction: highest-bidding builder wins
    6. Execute winning block against the pool (update pool state)
    7. Record MEV extracted, builder identity, block value
```

**Transaction generation:**
- Draw `amount_in ~ LogNormal(μ, σ)`
- Draw `gas_price ~ Pareto(α)` (fat-tailed, matching empirical gas distributions)
- Set `min_amount_out = amm_quote(amount_in) * (1 - slippage_tolerance)`
- Assign random `token_pair` from a small set (3-5 pairs, each backed by a separate AMM pool)

**State management:**
- The AMM pool state carries over between blocks (trades move the price)
- Implement pool rebalancing events (random large trades from "external" LPs) to prevent price drift to zero

---

### 13. `src/simulation/metrics.py` — MEV Accounting

Track per-block and aggregate statistics:

```python
@dataclass
class BlockMetrics:
    block_number: int
    builder_type: str
    information_param: float
    mev_extracted: float       # total profit from injected txns
    sandwich_count: int
    arbitrage_count: int
    failed_sandwich_count: int  # sandwiches that failed due to slippage
    gas_spent_on_mev: float
    user_slippage_cost: float   # harm imposed on users
    block_value: float          # total fees + MEV to builder
```

**Derived metrics for the paper:**
- `mev_rate(I)` = `mean(mev_extracted)` over blocks at fixed `I`
- `mev_recovery_curve` = `mev_rate(I) / mev_rate(I=1)` — fraction of full-information MEV recovered
- `user_harm_rate(I)` = `mean(user_slippage_cost)` — welfare metric
- `collusion_breakeven_cost(I)` — value of `c` where colluding builder net profit = 0

---

### 14. `experiments/run_full_sweep.py` — The Core Experiment

This script produces the paper's main results. It runs the simulation across a grid of parameters:

```
I_values     = [0.0, 0.1, 0.2, ..., 1.0]   (11 points)
L_values     = [100k, 500k, 1M, 5M, 10M]    (5 liquidity levels)
alpha_values = [0.0, 0.25, 0.5, 0.75, 1.0]  (5 inference accuracies)
```

For each `(I, L, α)` combination, run `n_blocks=1000` simulation blocks and record aggregate metrics.

Total runs: 11 × 5 × 5 = 275 configurations × 4 builder types = 1100 simulation runs.

**Parallelism:** Use `multiprocessing.Pool` to run configurations in parallel — each run is independent.

**Output:** Save results as a CSV with columns `[I, L, alpha, builder_type, mev_rate, user_harm_rate, ...]` for downstream analysis.

---

### 15. `experiments/phase_diagrams.py` — Key Figures

Generate the paper's main figures:

**Figure 1: MEV Recovery Curve**
- X-axis: `I` (information parameter)
- Y-axis: `mev_rate / mev_rate(I=1.0)` (normalized MEV)
- One line per builder type
- Expected shape: flat near 0 for random/inference builders at low I, rising sigmoid for maximal builder

**Figure 2: Phase Diagram (I vs L)**
- Heatmap of `mev_rate(I, L)`
- Shows the "safe zone" (low MEV) vs "danger zone" (high MEV)
- Expected: MEV is low at low I regardless of L; at high I, MEV grows with L

**Figure 3: Collusion Breakeven**
- X-axis: collusion cost `c`
- Y-axis: net profit for colluding builder
- One line per `I` value
- Zero-crossing gives minimum cost to deter collusion

**Figure 4: MEV vs. Inference Accuracy α (at I=0)**
- Shows MEV recovery purely from metadata inference
- Expected: near-zero at α=0, rising with α, but asymptotically below I=1 curve (inference can't fully replace visibility)

---

## Implementation Order (Suggested)

1. `transaction.py` + `public.py` — get data structures right first
2. `amm/pool.py` — core pricing engine; validate analytically
3. `maximal_builder.py` + `sandwich.py` — get MEV calculation correct against public mempool
4. `random_builder.py` + `engine.py` + `metrics.py` — get the simulation loop running end-to-end
5. `encrypted.py` + `partial.py` — add information parameter; verify MEV drops at I=0
6. `inference_builder.py` — add probabilistic recovery
7. `colluding_builder.py` — add cost model
8. `pbs/block_construction.py` — add auction layer
9. `run_full_sweep.py` — parallelize and run the full grid
10. `phase_diagrams.py` — produce final figures

---

## Critical Implementation Pitfalls to Avoid

1. **Slippage validation:** A sandwich is only valid if the victim transaction does NOT revert after the front-run. Always check `simulated_victim_out >= victim.min_amount_out` before counting the profit.

2. **Gas cost accounting:** Every injected transaction costs gas. MEV is *net* profit: `sandwich_profit - 2 * gas_cost_per_txn`. At low spreads, gas cost dominates and MEV is negative — this is economically correct.

3. **Pool state mutation:** Never mutate the live pool state while scanning for opportunities. Use `pool.fork()` for all speculative simulations.

4. **Information parameter semantics:** `I` must be operationally defined with a precise mapping to `leakage_rate` and `noise_sigma`. Document this mapping explicitly in `config.py` with a comment explaining the approximation.

5. **Baseline validity:** The random builder should extract near-zero MEV on average. If it extracts substantial MEV, the transaction generation is producing trivially sandwichable sequences that don't require strategy.

6. **α vs I independence:** In the partial regime, `α` (inference accuracy) and `I` (leakage rate) are separate parameters. At `I=0`, a builder with `α=1` can still extract MEV by perfect inference from metadata. This independence is a key finding to demonstrate.

---

## Formal Model Summary (for Paper Section 3)

The MEV profitability function is:

```
π(I, L, D, α) = E[max(0, sandwich_profit(I, L, D, α) - gas_cost)]
```

where:
- `I ∈ [0,1]` is the information parameter (fraction of transaction payload visible or inferable)
- `L` is AMM liquidity depth (= `x + y` in reserve units)
- `D` is the trade size distribution (parameterized by `μ_D, σ_D` of the log-normal)
- `α` is the inference accuracy of the builder's estimator

For the constant-product AMM with fee `f`, the sandwich profit under full information is:
```
π_full(v, L) = v * (1-f) / sqrt(L) * [correction term for fee and discrete arithmetic]
```

Under partial information, the effective profit is:
```
π(I, α) = I * π_full + (1-I) * α * E[π_full | metadata] - (1-I) * (1-α) * gas_cost
```

The threshold condition for profitable MEV extraction:
```
π(I, α) > 0
⟺ I > I*(α, L, D) = some threshold that decreases in α and L
```

This threshold `I*` is the primary quantity to estimate from simulations.

---

## Expected Results and Falsifiability

| Hypothesis | Expected Result | Falsified If |
|---|---|---|
| MEV collapses at I=0 for maximal builder | `mev_rate(I=0) ≈ 0` for maximal builder | Maximal builder extracts >5% of I=1 MEV at I=0 |
| Inference builder recovers MEV at I=0 | `mev_rate(I=0, α=0.8) > 0` for inference builder | MEV stays near zero even at high α |
| Collusion becomes unprofitable above cost threshold | Zero-crossing exists in `net_profit(c)` | Net profit is always positive or always negative |
| MEV grows with liquidity at fixed I | `mev_rate(I, L)` increasing in L | MEV flat or decreasing in L |
| Phase boundary exists in (I, L) space | Clear transition in heatmap | No discernible structure in phase diagram |
