# MEV Under Partial Mempool Privacy

**Team:** Owen Bartlett, Jacob Gutsin
**Course:** Blockchains Final Project

## Project

Simulation-based study of how mempool information regimes affect MEV extraction under Proposer-Builder Separation (PBS). We model four adversarial builder types across three visibility settings using an AMM-based simulation framework.

## Quick Start

```bash
pip install -r requirements.txt
python experiments/run_baseline.py        # single sanity-check run
python experiments/run_full_sweep.py      # full parameter sweep (slow)
python experiments/phase_diagrams.py      # generate figures from results/
```

## Structure

See [`PLAN.md`](PLAN.md) for the full implementation guide, formal model, and expected results.

## Adversary Types

| Builder | Strategy | Information Used |
|---|---|---|
| Random | Random ordering | None |
| Maximal | Optimal sandwich/arb | Full payload (when visible) |
| Colluding | Paid decryption | Purchased at cost `c` |
| Inference | Bayesian estimation | Metadata + prior |

## Information Parameter

`I ∈ [0,1]` maps to:
- `I = 0` → Threshold-encrypted mempool (payload hidden)
- `I = 1` → Public mempool (full visibility)
- `I ∈ (0,1)` → Partial-information (metadata leakage)
