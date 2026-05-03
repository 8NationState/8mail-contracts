# 8mail-contracts

Sealed-sender on-chain messaging contracts for the Octra network.

Part of the [8NationState](https://github.com/8NationState) privacy-infrastructure stack.

## Design principle

**Only sender and receiver can decrypt.** No committees, no threshold keys, no centralized relayers. The entire app lives on Octra — contracts on-chain, frontend on IPFS/Arweave, no off-chain servers holding message data or keys.

This is the anti-compellability property: no third party can be subpoenaed to decrypt messages because no third party holds the keys.

## Status

| Contract | File | Status | Address |
|---|---|---|---|
| `mail_sealed` | `contracts/mail_sealed.aml` | **Live — mainnet** | `octDRHQfDyLaahN8cpuqqJdrHUYDr67PnWETA5iby3gqVZd` |
| `mail_fhe` (v1) | `legacy/mail_fhe.aml` | Superseded — do not use | `oct7udTqtR1MJ5YpEovFBeCRywPxD9ZC7vp73TWzrBhnmD8` |
| `mail_fhe_v2` | `legacy/mail_fhe_v2.aml` | Never deployed | — |

Deploy tx: [`1411b7bd…2457ea7e`](http://46.101.86.250:8080) at epoch 756944. Bytecode SHA256 `fa2b605fcb329815ee91269eb7acd9684b5a1c598cfbb28f48c3d70d8aebe8c4`.

## `mail_sealed.aml` — the live contract

Sealed-sender messaging with anonymous membership set. Design decisions:

- **Membership as a Merkle commitment.** Users register an opaque leaf (`H(pubkey)` or `H(pubkey ‖ salt)`). The contract stores only a 16-level Merkle root; the member set is never enumerable on-chain.
- **Envelopes, not addresses.** `send_sealed(envelope)` stores an opaque blob. The recipient's identity is encrypted inside the envelope; the chain sees only that a registered member posted some bytes.
- **Fees are optional and owner-tunable.** Currently `50_000 OU` (0.05 OCT) per send; set to `0` to make sends free. Collected fees accumulate in `pending_fees` and are swept to `treasury` via permissionless `sweep()`.
- **Two-step ownership.** `initiate_owner_transfer(new_owner)` sets `pending_owner`; the new owner must call `accept_ownership()` from their own wallet. Prevents typo-induced admin loss. `cancel_owner_transfer()` available while pending.
- **No relayer in the contract.** Network-layer traceability reduction (Tor, Dandelion++, mixnets) is a client-side concern. Putting a relayer on-chain would not have hidden IP addresses and would have added attack surface for no privacy gain.

### Public API

Views (read-only, free):

| Fn | Returns |
|---|---|
| `owner()` | current owner address |
| `pending_owner()` | address awaiting `accept_ownership()`, or empty |
| `treasury()` | fee destination |
| `fee_per_send()` | current fee in OU |
| `pending_fees()` | accumulated unswept fees |
| `total_fees_collected()` | lifetime fees paid out |
| `merkle_root()` | current member-set commitment |
| `member_count()` | number of registered members |
| `next_msg_id()` | id that the next envelope will receive |
| `get_envelope(msg_id)` | the stored envelope blob |
| `is_member(leaf)` | membership proof-free check (deprecated — use Merkle proof) |

Calls (write, consume nonce):

| Fn | Semantics |
|---|---|
| `register(leaf, proof[])` | add leaf to member tree, advance root |
| `send_sealed(envelope)` | charge fee, store envelope, emit msg_id |
| `sweep()` | move `pending_fees` to `treasury`; permissionless |
| `set_fee(int)` | owner-only; update fee per send |
| `set_treasury(addr)` | owner-only; rotate fee destination |
| `initiate_owner_transfer(addr)` | owner-only; set `pending_owner` |
| `accept_ownership()` | must be called by `pending_owner` |
| `cancel_owner_transfer()` | owner-only; clear `pending_owner` |

See `contracts/mail_sealed.abi.json` for the full signature set.

## Layout

```
contracts/
  mail_sealed.aml                     # AML source
  mail_sealed.bytecode.b64            # deployed bytecode (base64)
  mail_sealed.abi.json                # ABI
  mail_sealed.deployment.json         # deploy record + verified state snapshot
scripts/
  deploy_sealed.py                    # deploy a fresh instance
legacy/
  mail_fhe.aml                        # v1 FHE design, superseded
  mail_fhe_v2.aml                     # v2 FHE draft, never deployed
  deploy_v2.py                        # FHE deploy script, retained for reference
```

## Deploying your own instance

The live contract at `octDRHQfDyLaahN8cpuqqJdrHUYDr67PnWETA5iby3gqVZd` is the canonical 8mail deployment. You do **not** need to redeploy to use 8mail — point your client at that address.

If you want an independent instance (e.g. for testing, a fork, or a private group), `scripts/deploy_sealed.py` will do it. You need:

1. A signer process exposing a unix socket (we use a local signer oracle).
2. A funded deployer wallet (deploy cost is `50 OCT` exactly).
3. Environment set:

   ```bash
   export OCTRA_RPC=http://46.101.86.250:8080/rpc
   export OCTRA_DEPLOYER=oct...your-wallet...
   export OCTRA_SIGNER_DIR=/path/to/your/signer/client
   export OCTRA_SIGNER_SOCK=/tmp/octra_signer.sock   # optional
   ```

4. Run:

   ```bash
   python scripts/deploy_sealed.py                 # dry run
   python scripts/deploy_sealed.py --confirm       # broadcast
   ```

The script re-verifies the bytecode SHA before signing and waits for tx confirmation before writing a fresh `deployment.json`.

## Security notes

- Audited? **No.** This is alpha software. Do not send money-denominated messages.
- Keys? **Your problem.** No recovery path. Lose the key, lose the inbox.
- IP privacy? **Not provided by the contract.** Use Tor or a similar transport if that matters to you.
- Ownership centralization? The owner can change the fee and treasury but cannot read messages or remove members. Plan is to migrate to a multisig or a null-owner once the fee schedule stabilizes.

## License

See [LICENSE](./LICENSE).
