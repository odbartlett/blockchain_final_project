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

# Rebalance the pool every this many blocks to prevent price drift.
# With bidirectional trades the price random-walks; rebalancing keeps it bounded.
_REBALANCE_EVERY = 10


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
    log_mean = np.log(config.trade_size_mean)
    txns = []

    for _ in range(n):
        # Draw trade size from log-normal
        amount_in = max(1, int(np_rng.lognormal(mean=log_mean, sigma=config.trade_size_sigma)))

        # Draw gas price from Pareto (fat-tailed)
        gas_price = int((np_rng.pareto(config.gas_price_pareto_alpha) + 1) * config.gas_cost_per_txn)

        # Random token pair
        pair = rng.choice(config.token_pairs)
        token_in, token_out = pair.split("/")

        # Deadline 1-10 blocks ahead
        deadline = block_number + rng.randint(1, 10)

        # Compute min_amount_out using initial reserves as proxy for current price.
        # This gives the correct AMM quote (with fee and price impact) * (1 - tolerance).
        # Uses initial reserves since generate_transactions has no live pool access.
        x0 = config.initial_reserves_x
        y0 = config.initial_reserves_y
        amount_in_eff = amount_in * (1 - config.amm_fee)
        estimated_out = int(amount_in_eff * y0 / (x0 + amount_in_eff))
        min_amount_out = max(1, int(estimated_out * (1 - config.slippage_tolerance)))

        txn = Transaction.from_visible(
            sender=f"user_{rng.randint(0, 99999)}",
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            min_amount_out=min_amount_out,
            gas_price=gas_price,
            deadline=deadline,
            current_block=block_number,
        )
        txns.append(txn)

    return txns


def _apply_block_to_pool(block: list[Transaction], pool: AMMPool) -> None:
    """
    Apply a block's transactions to the pool in order, advancing the pool state.
    Skips transactions where amount_in is None (encrypted, unresolved).
    """
    for tx in block:
        if tx.amount_in is None or tx.amount_in <= 0:
            continue
        if tx.token_in not in (pool.token_x, pool.token_y):
            continue
        # Guard against pool depletion
        reserve_out = pool.reserve_y if tx.token_in == pool.token_x else pool.reserve_x
        amount_in_eff = tx.amount_in * (1 - pool.fee)
        amount_out = int(amount_in_eff * reserve_out / (
            (pool.reserve_x if tx.token_in == pool.token_x else pool.reserve_y) + amount_in_eff
        ))
        if amount_out >= reserve_out:
            continue  # would deplete pool; skip
        pool.swap(tx.token_in, tx.amount_in)


def _rebalance_pool(pool: AMMPool, target_x: int, target_y: int) -> None:
    """
    Inject a market-maker swap to restore pool reserves toward (target_x, target_y).
    This models arbitrageurs and LPs that keep the AMM close to fair value.

    The swap brings the product reserve_x * reserve_y back toward target_x * target_y
    and the price back toward target_y / target_x.
    """
    # Compute the swap needed to restore price to target_y / target_x
    # For constant-product: after swap, new_x * new_y = k (approximately preserved)
    # Target price p = target_y / target_x → new_x = sqrt(k / p), new_y = sqrt(k * p)
    k = pool.reserve_x * pool.reserve_y
    target_price = target_y / target_x
    desired_x = int((k / target_price) ** 0.5)
    desired_y = int((k * target_price) ** 0.5)

    if desired_x > pool.reserve_x:
        # Need more token_x in pool → swap token_y for token_x
        diff = desired_x - pool.reserve_x
        if diff > 0 and diff < pool.reserve_y:
            pool.swap(pool.token_y, diff)
    elif desired_y > pool.reserve_y:
        # Need more token_y in pool → swap token_x for token_y
        diff = desired_y - pool.reserve_y
        if diff > 0 and diff < pool.reserve_x:
            pool.swap(pool.token_x, diff)


def _measure_block_metrics(
    block: list[Transaction],
    pool_before: AMMPool,
    builder_type: str,
    information_param: float,
    inference_accuracy: float,
    collusion_spend: float = 0.0,
    gas_per_txn: float = 2.0,
    true_txns: dict[str, Transaction] | None = None,
) -> BlockMetrics:
    """
    Execute block on pool_before fork and compute full BlockMetrics.

    Tracks:
    - mev_extracted: net builder profit from BUILDER-injected transactions
    - sandwich_count: number of sandwich front-runs in the block
    - gas_spent_on_mev: gas cost of all injected transactions
    - user_slippage_cost: extra slippage imposed on sandwiched victims vs no-MEV baseline
    - block_value: total builder revenue (MEV + user fees)

    true_txns: mapping tx_id → original unredacted Transaction.
    Needed because encrypted transactions in the block have amount_in=None, but they
    DO execute on-chain with their true amounts when the encryption is lifted.
    If provided, replaces redacted payloads during execution (not wallet tracking).
    """
    fork = pool_before.fork()
    wallet_x: float = 0.0
    wallet_y: float = 0.0

    sandwich_count = 0
    user_slippage_cost = 0.0
    total_user_fees = 0.0
    prev_tx_was_front = False   # detect sandwich triples: front → victim → back

    def _resolve(tx: Transaction) -> Transaction:
        """Return the unredacted version of tx if true_txns lookup is available."""
        if true_txns and tx.amount_in is None and tx.tx_id in true_txns:
            return true_txns[tx.tx_id]
        return tx

    # Pre-compute victim quotes without any front-runs for slippage cost measurement
    no_mev_fork = pool_before.fork()
    victim_baseline: dict[str, int] = {}
    for tx in block:
        if getattr(tx, "sender", None) == "BUILDER":
            continue
        resolved = _resolve(tx)
        if resolved.amount_in is not None and resolved.token_in == pool_before.token_x:
            victim_baseline[resolved.tx_id] = no_mev_fork.swap(resolved.token_in, resolved.amount_in)
        elif resolved.amount_in is not None:
            no_mev_fork.swap(resolved.token_in, resolved.amount_in)

    for i, tx in enumerate(block):
        is_builder = getattr(tx, "sender", None) == "BUILDER"
        exec_tx = tx if is_builder else _resolve(tx)
        if exec_tx.amount_in is None:
            continue

        amount_out = fork.swap(exec_tx.token_in, exec_tx.amount_in)

        if is_builder:
            if exec_tx.token_in == fork.token_x:
                wallet_x -= exec_tx.amount_in
                wallet_y += amount_out
                # This is a front-run if the transaction 2 slots later is also BUILDER
                if i + 2 < len(block) and getattr(block[i + 2], "sender", None) == "BUILDER":
                    sandwich_count += 1
            else:
                wallet_y -= exec_tx.amount_in
                wallet_x += amount_out
        else:
            total_user_fees += exec_tx.gas_price
            # Measure slippage cost for victims in sandwiches
            if exec_tx.tx_id in victim_baseline:
                baseline_out = victim_baseline[exec_tx.tx_id]
                slippage_harm = max(0, baseline_out - amount_out)
                user_slippage_cost += slippage_harm

    # Convert any remaining token_y balance to token_x at current price
    if fork.reserve_y > 0:
        wallet_x += wallet_y * fork.reserve_x / fork.reserve_y

    gas_spent_on_mev = sandwich_count * 2 * gas_per_txn

    return BlockMetrics(
        block_number=0,  # caller sets this
        builder_type=builder_type,
        information_param=information_param,
        inference_accuracy=inference_accuracy,
        mev_extracted=wallet_x,
        sandwich_count=sandwich_count,
        gas_spent_on_mev=gas_spent_on_mev,
        user_slippage_cost=user_slippage_cost,
        block_value=max(0.0, wallet_x) + total_user_fees,
        collusion_spend=collusion_spend,
    )


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
            gas_per_txn=config.mev_gas_token_cost,
        )
    if "inference" in config.builder_types:
        builders["inference"] = InferenceBuilder(
            alpha=config.inference_accuracy,
            decision_threshold=config.decision_threshold,
            gas_per_txn=config.mev_gas_token_cost,
        )
    return builders


def run_simulation(config: SimConfig) -> dict[str, SimulationResults]:
    """
    Run the full simulation for all builder types in config.builder_types.
    Returns dict mapping builder_type -> SimulationResults.

    Per-block algorithm:
    1. Generate n_user_txns_per_block transactions (log-normal sizes)
    2. Wrap in mempool regime determined by information_param
    3. Each builder independently constructs a hypothetical block
    4. Measure MEV for each builder's block against the current pool state
    5. Advance pool state by applying a neutral random-order block
    6. Every _REBALANCE_EVERY blocks, inject a rebalancing swap to prevent
       price drift (models LP/arbitrageur activity)
    7. Record BlockMetrics for each builder each block
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
            config_collusion_cost=config.collusion_cost_per_tx,
            builder_type=btype,
        )
        for btype in builders
    }

    for block_num in range(config.n_blocks):
        txns = generate_transactions(
            config.n_user_txns_per_block, config, block_num, rng, np_rng
        )
        mempool = make_mempool(txns, config)
        pool_snapshot = pool.fork()  # builders measure against this consistent state
        true_txns = {t.tx_id: t for t in txns}  # unredacted lookup for execution replay

        for btype, builder in builders.items():
            block = builder.build_block(mempool, pool_snapshot.fork(), config.block_gas_limit)

            collusion_spend = (
                builder.last_collusion_spend
                if hasattr(builder, "last_collusion_spend") else 0.0
            )

            metrics = _measure_block_metrics(
                block=block,
                pool_before=pool_snapshot,
                builder_type=btype,
                information_param=config.information_param,
                inference_accuracy=config.inference_accuracy,
                collusion_spend=collusion_spend,
                gas_per_txn=config.mev_gas_token_cost,
                true_txns=true_txns,
            )
            metrics.block_number = block_num
            results[btype].block_metrics.append(metrics)

        # Advance pool state: apply user transactions in random order (neutral baseline)
        neutral_txns = list(txns)
        rng.shuffle(neutral_txns)
        _apply_block_to_pool(neutral_txns, pool)

        # Periodic rebalancing to prevent price drift
        if (block_num + 1) % _REBALANCE_EVERY == 0:
            _rebalance_pool(pool, config.initial_reserves_x, config.initial_reserves_y)

    return results
