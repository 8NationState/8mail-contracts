#!/usr/bin/env python3
"""
Deploy rewritten mail_sealed.aml — constructor edition.

Differences from deploy_and_bootstrap.py (previous attempt that sunk 50 OCT at
oct8TT96…useP):

  F1 fix: contract now has `constructor(initial_root, initial_treasury, initial_fee)`.
          No fn init(), no bootstrap. State is written atomically at deploy.

  F2 fix: init args on the wire are BARE POSITIONAL JSON (not typed wrappers).
          message = json.dumps([zero_root_hex, treasury, fee_per_send]).

  F3 fix: removed bootstrap pattern entirely. Single deploy tx. No nonce+2.

  F4 fix: contract receives zero_root as a 64-char hex STRING, not 32 raw bytes.
          Caller must pass zero_root.hex() (what we already did for bootstrap).

Bytecode SHA256: fa2b605fcb329815ee91269eb7acd9684b5a1c598cfbb28f48c3d70d8aebe8c4

Usage:
    python deploy_sealed_v2.py                  # dry run, prints tx envelope
    python deploy_sealed_v2.py --confirm        # broadcast

Pre-flight:
    1. Start your signer (must expose a unix socket at $OCTRA_SIGNER_SOCK,
       default /tmp/octra_signer.sock).
    2. Set env vars:
         OCTRA_RPC          e.g. http://46.101.86.250:8080/rpc
         OCTRA_DEPLOYER     your deployer wallet address (oct...)
         OCTRA_SIGNER_DIR   path to a dir containing the signer client module
         OCTRA_SIGNER_SOCK  (optional) unix socket path
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parent.parent
CONTRACTS    = REPO_ROOT / "contracts"

RPC          = os.environ.get("OCTRA_RPC", "http://46.101.86.250:8080/rpc")
DEPLOYER     = os.environ.get("OCTRA_DEPLOYER", "")
TREASURY     = os.environ.get("OCTRA_TREASURY", DEPLOYER)  # defaults to deployer
FEE_PER_SEND = int(os.environ.get("OCTRA_FEE_OU", "50000"))  # 0.05 OCT
DEPLOY_OU    = os.environ.get("OCTRA_DEPLOY_OU", "50000000")  # 50 OCT
TREE_DEPTH   = 16

BYTECODE_B64 = (CONTRACTS / "mail_sealed.bytecode.b64").read_text().strip()
EXPECTED_SHA = "fa2b605fcb329815ee91269eb7acd9684b5a1c598cfbb28f48c3d70d8aebe8c4"

SIGN_CLIENT_DIR = os.environ.get("OCTRA_SIGNER_DIR", "")
if not SIGN_CLIENT_DIR:
    sys.exit("ERROR: set OCTRA_SIGNER_DIR to the path of your signer client")
if not DEPLOYER:
    sys.exit("ERROR: set OCTRA_DEPLOYER to your deployer wallet address")
sys.path.insert(0, SIGN_CLIENT_DIR)


def rpc(method, params, tout=20):
    body = json.dumps({"jsonrpc": "2.0", "method": method,
                       "params": params, "id": 1}).encode()
    req = urllib.request.Request(
        RPC, data=body, headers={"Content-Type": "application/json"}
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    r = json.loads(opener.open(req, timeout=tout).read())
    if "error" in r:
        raise RuntimeError(f"RPC {method} error: {r['error']}")
    return r["result"]


def compute_zero_root(depth: int) -> bytes:
    """keccak256 Merkle root of an all-zero tree at given depth (must match
    contract's internal zero-root derivation)."""
    from Crypto.Hash import keccak
    def k(d):
        h = keccak.new(digest_bits=256); h.update(d); return h.digest()
    current = k(b"")
    for _ in range(depth):
        current = k(current + current)
    return current


def sha256_hex(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="Broadcast (omit for dry run)")
    args = ap.parse_args()
    dry_run = not args.confirm

    print("=" * 72)
    print("  8mail mail_sealed.aml — constructor deploy")
    print("=" * 72)

    # Bytecode integrity
    actual_sha = sha256_hex(BYTECODE_B64)
    if actual_sha != EXPECTED_SHA:
        print(f"[FATAL] bytecode SHA mismatch")
        print(f"  expected: {EXPECTED_SHA}")
        print(f"  actual:   {actual_sha}")
        sys.exit(1)
    print(f"[bytecode_sha]  {actual_sha}  OK")

    bytecode = base64.b64decode(BYTECODE_B64)
    print(f"[bytecode_size] {len(bytecode)} bytes ({len(BYTECODE_B64)} b64 chars)")

    # Pre-flight: account state
    acct = rpc("octra_account", [DEPLOYER])
    balance = int(acct["balance_raw"])
    nonce = int(acct.get("nonce", 0))
    print(f"[deployer]      {DEPLOYER}")
    print(f"[balance]       {balance/1_000_000:.6f} OCT ({balance} OU)")
    print(f"[nonce]         {nonce}  (next = {nonce+1})")

    if balance < 60_000_000:
        print(f"[FATAL] balance < 60 OCT safety floor (deploy needs 50 OCT + headroom)")
        sys.exit(1)

    # Compute deterministic contract address
    addr_res = rpc("octra_computeContractAddress",
                   [BYTECODE_B64, DEPLOYER, nonce + 1])
    contract_addr = addr_res["address"]
    print(f"[contract_addr] {contract_addr}")

    # Guard: must NOT collide with prior broken deploy
    if contract_addr == "oct8TT96bfhENkN6udPFTbQ1PRUMT5fQjjrM4449ubPUseP":
        print(f"[FATAL] computed address matches prior broken deploy — refusing")
        sys.exit(1)

    # Constructor args: BARE POSITIONAL, hex string for root
    zero_root = compute_zero_root(TREE_DEPTH)
    init_args = [zero_root.hex(), TREASURY, FEE_PER_SEND]
    print(f"[zero_root]     {zero_root.hex()}")
    print(f"[treasury]      {TREASURY}")
    print(f"[fee_per_send]  {FEE_PER_SEND} OU ({FEE_PER_SEND/1_000_000:.6f} OCT)")

    # Canonical deploy tx. Field order & names MUST match prior working deploys
    # (see deploy_and_bootstrap.py) because signer uses this layout.
    deploy_tx = {
        "from":           DEPLOYER,
        "to_":            contract_addr,
        "amount":         "0",
        "nonce":          nonce + 1,
        "ou":             DEPLOY_OU,
        "timestamp":      time.time(),
        "op_type":        "deploy",
        "encrypted_data": BYTECODE_B64,
        "message":        json.dumps(init_args),  # BARE POSITIONAL — critical
    }

    print("\n[tx envelope]")
    preview = {k: v for k, v in deploy_tx.items() if k != "encrypted_data"}
    preview["encrypted_data"] = f"<b64 {len(BYTECODE_B64)} chars>"
    print(json.dumps(preview, indent=2))

    if dry_run:
        print("\n[DRY RUN] All checks passed. Pass --confirm to broadcast.")
        print(f"[DRY RUN] Next action: {DEPLOY_OU} OU ({int(DEPLOY_OU)/1_000_000} OCT) will leave deployer.")
        return

    # Broadcast
    from sign_client import OctraSigner  # noqa: E402

    print("\n[BROADCAST] signing + submitting …")
    signer = OctraSigner()
    result = signer.sign_and_submit(deploy_tx)

    rpc_result = result.get("rpc_result", {})
    if "error" in rpc_result:
        print(f"\n[FATAL] deploy failed: {rpc_result['error']}")
        sys.exit(2)

    # Signer returns the full JSON-RPC envelope as `rpc_result`, so the tx hash
    # lives at rpc_result["result"]["tx_hash"]. Fall back to flat keys and to
    # the signer envelope in case of schema drift. If still not found, query
    # the chain by deployer nonce so we never lose the hash silently.
    inner = rpc_result.get("result") if isinstance(rpc_result, dict) else None
    tx_hash = None
    for src in (inner, rpc_result, result):
        if isinstance(src, dict):
            tx_hash = src.get("tx_hash") or src.get("hash")
            if tx_hash:
                break

    if not tx_hash:
        print("\n[WARN] tx_hash not in signer response — recovering from chain …")
        try:
            import urllib.request as _u
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "octra_transactionsByAddress",
                               "params": [DEPLOYER]}).encode()
            req = _u.Request(RPC, data=body,
                             headers={"Content-Type": "application/json"})
            opener = _u.build_opener(_u.ProxyHandler({}))
            resp = json.loads(opener.open(req, timeout=15).read())
            for t in resp.get("result", {}).get("transactions", []):
                if (t.get("op_type") == "deploy"
                        and t.get("to") == contract_addr):
                    tx_hash = t.get("hash")
                    break
        except Exception as e:
            print(f"[WARN] recovery query failed: {e}")

    print(f"[tx_hash]       {tx_hash or '<UNKNOWN — see full signer envelope below>'}")
    if not tx_hash:
        print("\n[DEBUG] full signer envelope:")
        print(json.dumps(result, indent=2, default=str)[:2000])

    # Persist
    record = {
        "network":        "mainnet",
        "deployer":       DEPLOYER,
        "contract_addr":  contract_addr,
        "deploy_tx":      tx_hash,
        "init_args":      init_args,
        "bytecode_sha":   EXPECTED_SHA,
        "bytecode_size":  len(bytecode),
        "timestamp":      deploy_tx["timestamp"],
        "notes":          "constructor deploy; atomic state init; replaces abandoned oct8TT96…useP",
    }
    out = CONTRACTS / "mail_sealed.deployment.json"
    # backup previous record if present
    if out.exists():
        backup = CONTRACTS / f"mail_sealed.deployment.prev.{int(time.time())}.json"
        backup.write_text(out.read_text())
        print(f"[backup]        previous record -> {backup.name}")
    out.write_text(json.dumps(record, indent=2))
    print(f"[saved]         {out}")

    print("\n[NEXT]")
    print("  1. Wait ~30-60s for finality.")
    print(f"  2. Verify: curl -sS -X POST {RPC} \\")
    print(f"       -d '{{\"jsonrpc\":\"2.0\",\"method\":\"octra_tx\",\"params\":[\"{tx_hash}\"],\"id\":1}}'")
    print("  3. Query views via contract_call: get_owner, get_treasury,")
    print("     get_fee_per_send, current_root — all should return non-zero.")
    print("  4. Update 8mail-cli config with new contract_addr.")


if __name__ == "__main__":
    main()
