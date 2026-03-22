# Code Explanation: MEV Under Partial Mempool Privacy

This document explains every file implemented so far and walks through how a single
experiment flows from configuration to MEV measurement.

---

## 1. The Information Parameter `I`

The central idea in this project is that a block builder's ability to extract MEV
depends on how much they can see. We capture this with a single number `I ∈ [0, 1]`:

- `I = 1.0` → **public mempool**: builder sees every transaction in full
- `I = 0.0` → **encrypted mempool**: builder sees only metadata, no trade sizes
- `I ∈ (0, 1)` → **partial mempool**: each transaction is revealed with probability `I`

Every other component in the codebase is downstream of this parameter.

---

## 2. File-by-File Explanation

### `src/simulation/config.py` — `SimConfig`

The single source of truth for all tunable parameters. Nothing in the codebase uses
magic numbers; they all come from `SimConfig`. Key fields:

| Field | Meaning |
|---|---|
| `initial_reserves_x/y` | Starting AMM pool depth (default 1M / 1M, so initial price = 1) |
| `amm_fee` | Pool swap fee, 0.003 = 0.3% (Uniswap v2 default) |
| `trade_size_mean / sigma` | Log-normal trade size distribution parameters |
| `slippage_tolerance` | Victim's max acceptable price worsening, e.g. 0.01 = 1% |
| `information_param` | `I` — which mempool regime to use |
| `noise_sigma` | Relative noise on amount estimates in `PartialMempool` |
| `collusion_cost_per_tx` | Cost to "buy" a decryption in `ColludingBuilder` |
| `inference_accuracy` | `α` — how correlated the inference builder's estimate is to truth |

---

### `src/mempool/transaction.py` — `Transaction`

The unified representation of a pending transaction across all three information regimes.

**Two classes of fields:**

**Payload fields** (hidden when `payload_visible = False`):
- `sender`, `amount_in`, `min_amount_out`
- These are what the builder needs to execute a sandwich: exact trade size and
  the victim's slippage bound (which determines how large a front-run they can absorb)

**Metadata fields** (always visible, even in encrypted mempools):
- `metadata_gas_price` — identical to `gas_price`; a builder can rank by fee even blindly
- `metadata_size_bucket` — `"small"` / `"medium"` / `"large"` binned from `amount_in`
  using thresholds (500, 5000). This is the information that leaks even through
  encryption (analogous to packet-size side channels in real threshold schemes).
- `metadata_token_pair` — which pool the trade is going to
- `metadata_deadline_urgency` — `1 - (deadline - current_block) / 10`, clamped to [0,1].
  A value near 1 means the transaction expires soon; near 0 means it has a long window.

**`from_visible()` classmethod:**
Constructs a fully visible transaction and auto-computes all metadata from the raw fields.
This is what `generate_transactions` calls.

---

### `src/mempool/public.py` — `PublicMempool`

Trivial wrapper: `get_transactions()` returns all transactions unchanged with
`payload_visible = True`. Represents `I = 1.0`.

---

### `src/mempool/encrypted.py` — `EncryptedMempool`

Represents `I = 0.0`. For each transaction it calls `dataclasses.replace(t, sender=None, amount_in=None, min_amount_out=None, payload_visible=False)`.

`dataclasses.replace` creates a **new object** with the specified fields overwritten and
all other fields copied from the original. This is important: the original transaction
objects in the simulation's pool are not modified — only the builder's view is restricted.

---

### `src/mempool/partial.py` — `PartialMempool`

Represents `I ∈ (0, 1)`. For each transaction in `get_transactions()`:

1. Draw `r ~ Uniform(0, 1)`.
2. If `r < leakage_rate`: return the transaction fully revealed (`payload_visible=True`).
3. Otherwise: return a redacted copy where `amount_in` is replaced with a noisy estimate
   `amount_in_noisy ~ N(true_amount, noise_sigma * true_amount)`, clamped to ≥ 1, and
   `payload_visible=False` (so builders know the estimate is noisy, not exact).

The noisy amount leaks through `metadata_size_bucket` matching — a builder observing
a "large" bucket can infer the trade was at least 5000 units, but not the exact amount.

---

### `src/amm/pool.py` — `AMMPool`

The mathematical core of the simulation. Implements a Uniswap v2-style constant-product
AMM where `reserve_x * reserve_y = k` (invariant, approximately — fees actually
increase `k` slightly after each swap).

**`swap(token_in, amount_in) → amount_out`**

Applies the constant-product formula with fee deduction on the input side:
```
amount_in_eff = amount_in * (1 - fee)
amount_out    = amount_in_eff * reserve_out / (reserve_in + amount_in_eff)
```
**Mutates** `reserve_x` and `reserve_y` in place. Callers who need non-mutating
behavior must call `pool.fork()` first.

**`quote(token_in, amount_in) → amount_out`**

Identical to `swap` but forks the pool first, so the original state is unchanged.
Used by builders for planning.

**`price_impact(token_in, amount_in) → float`**

Returns `(price_after / price_before) - 1`. Positive when selling token_x (price of
token_x falls in token_y terms). Used to gauge how much a trade moves the market.

**`optimal_front_run(victim_amount) → int`**

The closed-form front-run size that maximises sandwich profit on a constant-product AMM
without fees:
```
f* = sqrt(reserve_x * (reserve_x + victim_amount)) - reserve_x
```
Derivation: the attacker profits by buying token_y cheap before the victim and selling
it back after. Profit is maximised when the attacker's marginal cost equals the
victim-induced price recovery — which yields the above square-root formula.

Note: this formula ignores fees and the victim's slippage constraint. The actual
profitable and valid front-run size may be smaller; the `sandwich_profit` check enforces
the slippage constraint.

**`sandwich_profit(front_amount, victim_amount, victim_min_out) → (profit, valid)`**

Simulates the full three-leg sequence on an internal fork:

1. **Front-run**: builder sends `front_amount` of `token_x` → receives `y_front` of `token_y`.
   Pool becomes richer in `token_x`, scarcer in `token_y` → price of `token_x` drops.

2. **Victim**: sends `victim_amount` of `token_x` → receives `victim_out` of `token_y`.
   Victim gets *less* than they would have without the front-run because pool already has
   more `token_x`. If `victim_out < victim_min_out`, the transaction would revert on-chain
   and the sandwich is **invalid** — returns `(0, False)`.

3. **Back-run**: builder sends `y_front` of `token_y` back into the pool → receives
   `x_back` of `token_x`. Pool now has more `token_y` than before step 2, so the back-run
   gets favourable rates.

Net profit (in `token_x`): `x_back - front_amount`. Positive because the victim's swap
moved the pool price further in the attacker's favour between front and back legs.

**`fork() → AMMPool`**

Returns `copy.deepcopy(self)`. Every builder uses this before speculative simulation
to avoid contaminating the live pool state.

---

### `src/mev/sandwich.py` — Sandwich Primitives

**`SandwichOp` dataclass**: packages a sandwichable victim transaction together with the
computed front-run size and expected profit. Used as the intermediate representation
between finding opportunities and building the block.

**`find_sandwich_opportunities(txns, pool) → list[SandwichOp]`**

Scans visible transactions for sandwichable swaps:
1. Skip any transaction where `payload_visible = False` — without exact `amount_in` and
   `min_amount_out` there is no basis for sandwich planning.
2. Skip transactions where `token_in != pool.token_x` — the pool only supports one
   swap direction for sandwich purposes (the victim must be selling the same token the
   builder is selling).
3. Compute `f* = pool.optimal_front_run(tx.amount_in)`.
4. Call `pool.sandwich_profit(f*, victim_amount, min_amount_out)` — this validates the
   slippage constraint and computes profit.
5. Keep only valid, profitable opportunities; sort by profit descending.

This function does **not** mutate the pool — `sandwich_profit` operates on an internal fork.

**`execute_sandwich(pool, front_amount, victim_txn) → (profit, valid)`**

Thin wrapper around `pool.sandwich_profit` for use by builders that want to re-check
profitability just before inserting into a block.

---

### `src/builders/base.py` — `Builder` (Abstract Base)

Defines the interface all builders share and provides the shared `compute_mev` method.

**`build_block(mempool, pool, block_gas_limit) → list[Transaction]`**

Abstract. Subclasses implement their ordering/injection strategy here.

**`compute_mev(block, pool) → float`**

Replays the block sequentially on a pool fork and tracks the net balance change of
any transaction where `sender == "BUILDER"`. Maintains two running totals:

- `wallet_x`: builder's net `token_x` position
- `wallet_y`: builder's net `token_y` position

After the front-run (builder sells `token_x`, receives `token_y`): `wallet_x < 0, wallet_y > 0`.
After the back-run (builder sells `token_y`, receives `token_x`): both return near zero.
The residual `wallet_x` (plus any remaining `wallet_y` converted at the final pool price)
is the MEV profit.

For a random builder with no injected transactions, `compute_mev` always returns 0.

---

### `src/builders/random_builder.py` — `RandomBuilder`

The zero-MEV baseline. `build_block`:
1. Gets all transactions from mempool (`get_transactions()` may return redacted copies).
2. Shuffles them in a random order.
3. Greedily packs transactions at 21,000 gas each until the block gas limit is hit.
4. Returns the list — no injected transactions, so `compute_mev` on this block = 0.

Its purpose is calibration: if the random builder's measured MEV is non-zero, the
transaction generation or MEV accounting has a bug.

---

### `src/builders/maximal_builder.py` — `MaximalBuilder`

The theoretical upper bound on MEV under a given information regime. This is the most
complex builder.

**`build_block` algorithm:**

1. **Filter to visible transactions**: only those with `payload_visible = True`. Under
   `I = 0.0` (encrypted mempool), this returns nothing — the builder cannot see any
   `amount_in` or `min_amount_out`, so no valid sandwich can be constructed. MEV → 0.

2. **Find sandwich opportunities**: delegates to `find_sandwich_opportunities`, which
   returns a profit-sorted list of `SandwichOp`.

3. **Greedy non-conflicting selection**: each sandwich costs 3 × 21,000 = 63,000 gas
   (front-run, victim, back-run). Sandwiches are added in profit-descending order,
   skipping any victim whose `tx_id` is already sandwiched. This prevents double-spending
   a victim — a transaction can only appear once in a block.

4. **Back-run amount calculation**: for each selected opportunity, the builder simulates
   the front-run on a fresh fork to determine exactly how much `token_y` they receive.
   This becomes the `amount_in` of the back-run transaction. This is a separate simulation
   from the one done in `find_sandwich_opportunities` because the pool state may have
   shifted slightly due to earlier sandwiches in the same block.

5. **Fill with high-fee user transactions**: remaining gas is filled with regular
   transactions sorted by `gas_price` descending.

**`_make_builder_txn` helper**: creates a `Transaction` with `sender = "BUILDER"`,
`gas_price = 0` (builder pays no fee to themselves), and `min_amount_out = 1` (builder
accepts any back-run output). This sentinel sender is what `compute_mev` uses to
distinguish injected transactions from user transactions.

---

### `src/simulation/engine.py` — `generate_transactions` and `run_simulation`

**`generate_transactions(n, config, block_number, rng, np_rng)`**

Produces `n` synthetic user transactions per block:

- `amount_in ~ LogNormal(log(trade_size_mean), trade_size_sigma)` drawn via numpy.
  The log-mean is `log(trade_size_mean)`, so the median trade size is `trade_size_mean`.
  With `sigma = 1.5`, the distribution has a fat right tail — most trades are small but
  occasional whale trades are much larger, creating high-profit sandwich targets.

- `gas_price ~ Pareto(alpha) * gas_cost_per_txn`, drawn via `np_rng.pareto` + 1 to get
  a shifted Pareto. Fat-tailed gas prices match empirical Ethereum gas distributions where
  most transactions pay the base fee but a few pay 10–100× for priority.

- `min_amount_out` is computed using the **AMM formula** against the initial reserves
  (not naively as `amount_in * 0.99`). This matters because for large trades, AMM price
  impact is significant — the victim might receive only 90% of `amount_in` in token_y
  terms. Using `amount_in * 0.99` as `min_amount_out` would produce transactions that
  would fail even without front-running, breaking sandwich validity.

**`make_mempool(txns, config)`**

Routes to the appropriate mempool class based on `config.information_param`:
- `I >= 1.0` → `PublicMempool`
- `I <= 0.0` → `EncryptedMempool`
- Otherwise → `PartialMempool(leakage_rate=I)`

**`run_simulation(config)`**

The main loop (partially complete — pool state advancement is a TODO stub):
- Creates one AMM pool and instantiates all builder types
- Each block: generates fresh transactions, wraps in a mempool, then has each builder
  independently construct and measure a hypothetical block against a pool fork
- Records `BlockMetrics` (MEV extracted, builder type, etc.) for analysis

---

## 3. Tracing a Single Experiment

Here is the exact sequence of calls when you run `run_simulation` with `I = 0.5`:

```
SimConfig(information_param=0.5, ...)
    │
    ├─ AMMPool(reserve_x=1M, reserve_y=1M, fee=0.003)
    │
    └─ for block_num in range(n_blocks):
         │
         ├─ generate_transactions(50, config, block_num, rng, np_rng)
         │     │
         │     ├─ For each of 50 txns:
         │     │     amount_in  ~ LogNormal(log(1000), 1.5)   → e.g. 4,200
         │     │     gas_price  ~ (Pareto(2.0) + 1) * 21,000  → e.g. 35,000
         │     │     token_pair ~ choice(["ETH/USDC","ETH/DAI","USDC/DAI"]) → "ETH/USDC"
         │     │     deadline   = block_num + randint(1,10)    → e.g. block_num + 3
         │     │     estimated_out = 4200*0.997*1M/(1M+4200*0.997) ≈ 4183
         │     │     min_amount_out = int(4183 * 0.99) = 4141
         │     │
         │     └─ Transaction.from_visible(...)
         │           → metadata_size_bucket = "medium"   (500 < 4200 <= 5000)
         │           → metadata_deadline_urgency = 1 - 3/10 = 0.7
         │
         ├─ make_mempool(txns, config)  [I=0.5]
         │     → PartialMempool(txns, leakage_rate=0.5, noise_sigma=0.3)
         │
         ├─ MaximalBuilder.build_block(mempool, pool.fork(), gas_limit)
         │     │
         │     ├─ mempool.get_transactions()
         │     │     → For each of 50 txns, flip coin with P=0.5:
         │     │         heads: return txn as-is (payload_visible=True, exact amount_in)
         │     │         tails: return redacted copy with
         │     │                  amount_in = N(4200, 0.3*4200) ≈ 3800  (noisy)
         │     │                  min_amount_out = None
         │     │                  payload_visible = False
         │     │
         │     ├─ visible = [txns where payload_visible=True]
         │     │     → ~25 of 50 transactions fully visible (on average)
         │     │
         │     ├─ find_sandwich_opportunities(visible, pool)
         │     │     → For each visible ETH-in txn:
         │     │           f* = sqrt(1M * (1M + amount_in)) - 1M
         │     │           pool.sandwich_profit(f*, amount_in, min_amount_out)
         │     │             → forks pool, runs front/victim/back simulation
         │     │             → returns (profit, valid)
         │     │     → Returns sorted list of SandwichOp
         │     │
         │     ├─ Greedily build block:
         │     │     [front_txn_BUILDER, victim_txn, back_txn_BUILDER,
         │     │      front_txn_BUILDER, victim_txn, back_txn_BUILDER,
         │     │      high_fee_user_txn, high_fee_user_txn, ...]
         │     │
         │     └─ Returns list[Transaction]
         │
         └─ MaximalBuilder.compute_mev(block, pool.fork())
               │
               ├─ fork = pool.fork()  [fresh 1M/1M copy]
               │
               ├─ For each txn in block:
               │     amount_out = fork.swap(txn.token_in, txn.amount_in)
               │     if txn.sender == "BUILDER":
               │         track wallet_x / wallet_y delta
               │
               └─ return wallet_x + wallet_y * (fork.reserve_x / fork.reserve_y)
                    = net profit in token_x units
```

### What changes at different values of `I`

| `I` | Mempool | `visible` after `get_transactions()` | Expected MEV |
|---|---|---|---|
| `1.0` | `PublicMempool` | All 50 txns, exact amounts | Maximum — all profitable sandwiches found |
| `0.5` | `PartialMempool(0.5)` | ~25 txns visible, ~25 with noisy amounts | ~50% of public MEV |
| `0.0` | `EncryptedMempool` | 0 txns (all have `payload_visible=False`) | ~0 — no valid sandwiches possible |

At `I = 0.0`, the `MaximalBuilder` enters `find_sandwich_opportunities` with an empty
`visible` list, finds zero opportunities, produces a block with no injected transactions,
and `compute_mev` returns 0. This is the key empirical claim of the paper.

---

## 4. Key Numerical Example

Pool: (1,000,000 ETH, 1,000,000 USDC), fee = 0.3%
Victim: swap 7,070 ETH → USDC, `min_amount_out` = 6,929 USDC

**Without sandwiching:** victim receives 6,999 USDC (as quoted by pool).

**With optimal front-run:**
```
f* = sqrt(1,000,000 * 1,007,070) - 1,000,000 = 3,528 ETH
```

1. Builder sends 3,528 ETH → receives 3,504 USDC; pool becomes (1,003,528 / 996,496)
2. Victim sends 7,070 ETH → receives 6,945 USDC (≥ 6,929 ✓); pool becomes (1,010,598 / 989,551)
3. Builder sends 3,504 USDC → receives 3,554 ETH; pool becomes (1,007,044 / 993,055)

**Builder profit: 3,554 − 3,528 = +26 ETH** (in token_x units, before gas costs)

The sandwich is valid because the victim still received 6,945 ≥ 6,929 (within 1% tolerance).

---

## 5. What is NOT yet implemented (as of modules 1–3)

The following builders are stubs (`raise NotImplementedError`):

- **`ColludingBuilder`** (module 7): pays a cost per transaction to "purchase" a
  decryption. Models the economic security threshold of threshold encryption schemes.
- **`InferenceBuilder`** (module 8): uses Bayesian inference over metadata to estimate
  `amount_in` for encrypted transactions and execute speculative sandwiches.

The simulation loop in `engine.py` also has two TODO stubs:
- Applying the winning block's transactions back to the pool (price evolution across blocks)
- Periodic rebalancing to prevent pool price drift to zero
