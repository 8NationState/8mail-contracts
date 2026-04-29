# 8mail-contracts

FHE-encrypted on-chain messaging contracts for the Octra network.

Part of the [8NationState](https://github.com/8NationState) privacy-infrastructure stack.

## Status

| Contract | File | Status | Address |
|---|---|---|---|
| Mail8FHE (v1) | `mail_fhe.aml` | **Deployed, alpha** | `oct7udTqtR1MJ5YpEovFBeCRywPxD9ZC7vp73TWzrBhnmD8` |
| Mail8FHEv2 | `mail_fhe_v2.aml` | Draft — not deployed | — |

## Design principle

**Only sender and receiver can decrypt.** No committees, no threshold keys, no centralized relayers. The entire app lives on Octra — contracts on-chain, frontend on IPFS/Arweave, no off-chain servers holding message data or keys.

This is the anti-compellability property: no third party can be subpoenaed to decrypt messages because no third party holds the keys.

## v1 — `mail_fhe.aml`

Minimal FHE messaging. End-to-end encrypted envelopes. Registration gate. E2E tested Alice → Bob on Octra mainnet alpha.

No fees. No revenue mechanism. Designed to prove the FHE primitive works.

## v2 — `mail_fhe_v2.aml` (draft)

Adds sustainable economics without centralizing:

- `fee_per_message`: default `10_000 OU` (0.01 OCT, ~$0.00019 at OCT = $0.019). Owner-tunable via `set_fee()`.
- `treasury`: address that receives accumulated fees via `sweep()`. Owner-tunable via `set_treasury()`.
- `pending_fees` / `total_fees_collected`: on-contract counters for transparency.
- Ownership transferable via `transfer_ownership()` — intended path: deploy-wallet → 8NS multisig → 8NS DAO timelock.
- Events: `FeeCollected`, `FeeUpdated`, `TreasuryUpdated`, `Swept`.

### Sweep pattern

v2 accumulates fees on the contract and exposes a permissionless `sweep()` that forwards the balance to `treasury`. Anyone can call it; funds always go to treasury. This avoids depending on AML supporting inline `transfer()` during `send_encrypted_message()` — if the VM supports auto-forwarding, we switch to direct forwarding in v3.

**DECISION NEEDED:** confirm AML `transfer(addr, amount)` semantics in dry-compile before deploy.

### Deploy

```bash
# pseudocode — plug into octra-webcli or Python deploy script
octra deploy mail_fhe_v2.aml \
  --init-args '{"initial_treasury": "octGFAk...bbW", "initial_fee": 10000}' \
  --gas-budget 150
```

Deploy cost empirically ~125 OCT per contract on Octra mainnet alpha.

## Governance

Ownership of deployed contracts is held by the 8NationState project. The path is:

1. **Phase 1 (now):** founder wallet owns contracts.
2. **Phase 2:** transfer ownership to 8NS multisig (community signers).
3. **Phase 3:** transfer ownership to 8NS DAO timelock after token launch.
4. **Phase 4:** parameter changes (`set_fee`, `set_treasury`) gated by binding on-chain votes.

See `governance/` (private) and forthcoming `8NS-dao-governance.md` for the full roadmap.

## License

Apache-2.0. See `LICENSE`.
