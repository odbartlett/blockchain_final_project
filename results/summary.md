# Experiment Summary: MEV Under Partial Mempool Privacy

**Authors:** Owen Bartlett & Jacob Gutsin
**Date:** March 2026

---

## What We Were Studying

When you submit a transaction to a blockchain, it sits in a waiting area called the **mempool** before being included in a block. Sophisticated block builders can read pending transactions and exploit them — most commonly through **sandwich attacks**: buying a token just before your trade (driving the price up), then selling it back immediately after (capturing the difference). This profit is called **MEV** (Maximal Extractable Value).

The central question of this project is: **does hiding transaction details from the mempool actually reduce MEV?**

Blockchain protocols like Ethereum's PBS (Proposer-Builder Separation) can encrypt mempool transactions so builders can't read them before including them in a block. We modeled a spectrum from fully public (I = 1) to fully encrypted (I = 0), and tested four different builder strategies against it.

---

## How the Simulation Works

We built an AMM (Automated Market Maker) — the same constant-product pricing model used by Uniswap — with 1 million units of each token. Each block, 50 synthetic user transactions are generated with realistic trade sizes (log-normal distribution) and gas prices (Pareto / fat-tailed). We then run four builder types simultaneously on each block and measure how much MEV each extracts.

**The four builders:**

| Builder | Strategy |
|---|---|
| **Random** | Includes transactions in random order — no MEV attempt |
| **Maximal** | Full sandwich attacks on every visible, profitable transaction |
| **Colluding** | Pays a fee to decrypt individual transactions, then sandwiches them |
| **Inference** | Never decrypts; uses only metadata (trade size bucket, gas price) to probabilistically guess trade sizes and speculate on sandwiches |

The **information parameter I** controls how much builders can see. At I = 1, all transaction amounts are visible. At I = 0, amounts are hidden and only coarse metadata (small/medium/large size bucket) is available. Values in between leak details probabilistically.

We ran 100-block simulations across all combinations and recorded average MEV per block for each builder.

---

## Figure 1: How Much MEV Can Builders Extract at Each Privacy Level?

Each builder's MEV is normalized to its own full-information baseline (I = 1), so 1.0 means "as much as with full visibility."

**What we found:**

- **Maximal builder** is completely neutralized by full encryption. At I = 0 it extracts zero MEV — it can't see trade amounts, so it can't size a sandwich. MEV rises smoothly and roughly linearly as information leaks in, reaching full extraction at I = 1.

- **Colluding builder** is nearly immune to encryption. Even at I = 0 it extracts ~914 tokens/block (93% of its fully-public baseline) because it *buys* the encrypted payloads directly from threshold committee members. Privacy protocols that rely on threshold encryption are only as strong as the economic incentives of the committee members — and if MEV > collusion cost, those incentives fail.

- **Inference builder** achieves ~164 tokens/block even at I = 0, using only metadata. This is roughly 16% of the maximal baseline (~1,029). Importantly, accuracy improvements (α) help only marginally (see Figure 4) — the main factor is whether you have *any* information at all, not how well you process it.

- **Random builder** extracts zero MEV at all I values — it serves as the user-welfare baseline. Any harm above zero in the other builders is purely a result of ordering manipulation.

**Takeaway:** Full encryption stops naive MEV (maximal builder), but does not stop sophisticated adversaries who can purchase information or reason from metadata alone.

---

## Figure 2: Does Liquidity Protect Users?

We varied both I and pool liquidity (reserves from 250K to 4M) and measured MEV for the maximal builder.

**What we found:**

- **More liquidity = less MEV per block.** At I = 1 and L = 4M, the maximal builder extracts only ~205 tokens/block. At the same I with L = 250K, it extracts ~4,079 tokens/block — 20× more.

- The intuition is straightforward: in a deep pool, a fixed-size trade causes less price impact, which means less sandwich profit per transaction.

- Crucially, **liquidity and encryption interact.** High liquidity at low I results in near-zero MEV even from a maximal builder — the two protections compound. But at high I, even a very liquid pool still suffers meaningful MEV.

**Takeaway:** Liquidity is a natural MEV dampener, but it doesn't substitute for privacy. The most protected environment combines deep liquidity *and* encrypted mempools.

---

## Figure 3: What Does It Cost to Deter Collusion?

The colluding builder pays a fee per transaction decrypted. We swept that cost from 0 to 2,000 tokens and measured net MEV (profit minus total collusion fees paid).

**What we found:**

- Net MEV drops sharply as collusion cost rises. The **breakeven cost** — where it stops being profitable to collude — is around **10–20 tokens per transaction** regardless of information level I.

- This is a surprisingly low threshold given that the gross MEV per sandwich is on the order of 90–180 tokens. The colluding builder only needs to decrypt ~7–10 transactions per block to hit the gas/fee limit, so even modest per-transaction fees make the strategy uneconomical.

- The breakeven is similar at I = 0, I = 0.5, and I = 1, which means that once a builder is willing to collude, the public visibility of the rest of the mempool doesn't change the economics much. The decision to collude is driven by MEV opportunity, not by how opaque the baseline is.

**Takeaway:** Threshold encryption can deter collusion if the committee members can credibly commit to a per-decryption fee above the breakeven (~10–20 tokens here). Protocol designers can directly target this threshold when setting cryptographic committee compensation.

---

## Figure 4: How Much Does Better Inference Help?

The inference builder uses metadata (size bucket, gas price, deadline urgency) to probabilistically guess trade sizes and place speculative sandwiches. The accuracy parameter α controls how well-calibrated its prior is: at α = 0, estimates are highly noisy; at α = 1, they cluster near the true bucket median.

**What we found:**

- Going from α = 0 (random guessing within a size bucket) to α = 1 (perfect bucket-median estimates) adds only **~14 tokens/block** — a 9% improvement over a baseline of ~151 tokens/block.

- Most of the inference builder's MEV comes simply from *knowing which size bucket a transaction falls in*, not from having a precise estimate within that bucket. The metadata signal is already largely captured by the coarse bucket label.

- This suggests that **hiding the size bucket** (or using bucket sizes broad enough to be uninformative) is a higher-value privacy improvement than improving the cryptographic noise model. The current three-bucket scheme (small/medium/large) leaks enough signal for ~16% MEV recovery even at I = 0.

**Takeaway:** Metadata inference is already nearly saturated at low α — the builder doesn't need sophisticated models to exploit size-bucket information. A well-designed private mempool must obscure even coarse metadata, not just exact amounts.

---

## Overall Conclusions

| Protection mechanism | Stops random/naive MEV? | Stops maximal MEV? | Stops colluding? | Stops inference? |
|---|---|---|---|---|
| Full encryption (I = 0) | Yes | Yes | No | Partially |
| High liquidity | Reduces | Reduces | Reduces | Reduces |
| Collusion fee > breakeven | N/A | N/A | Yes | N/A |
| Coarse metadata only | N/A | N/A | N/A | Partially |

1. **Encryption alone is not sufficient.** It stops the largest, simplest class of attack but leaves the protocol vulnerable to collusion and metadata inference.

2. **Collusion is the critical threat.** With a gross sandwich profit of ~100–180 tokens and a breakeven collusion cost of only ~10–20 tokens, threshold committee members have strong economic incentive to sell decryptions. The ratio of MEV opportunity to deterrence cost is the key design parameter for private mempool protocols.

3. **Metadata is underappreciated as a leakage surface.** An inference builder with no decryption ability captures ~16% of full-information MEV just from size buckets and gas prices. Private mempool designs should treat metadata as a first-class privacy concern.

4. **Liquidity and privacy are complementary, not substitutable.** Each reduces MEV independently and their combination is more effective than either alone.

---

## Files

| File | Contents |
|---|---|
| `results/sweep_results.csv` | Raw simulation output (134 rows across all parameter combinations) |
| `results/figures/figure1_mev_recovery_curve.png` | MEV vs information level, all builders |
| `results/figures/figure2_phase_diagram.png` | MEV heatmap over information × liquidity |
| `results/figures/figure3_collusion_breakeven.png` | Net MEV vs collusion cost at three I values |
| `results/figures/figure4_mev_vs_alpha.png` | MEV vs inference accuracy at I = 0 |
| `experiments/run_quick_sweep.py` | Runs the parameter sweep (100 blocks/run) |
| `experiments/phase_diagrams.py` | Generates all four figures from the CSV |
