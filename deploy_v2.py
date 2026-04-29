#!/usr/bin/env python3
"""
8mail v2 deploy — mail_fhe_v2.aml → Octra mainnet alpha.

v2 adds:
  - treasury: address
  - fee_per_message: int (default 10_000 OU = 0.01 OCT)
  - pending_fees / total_fees_collected counters
  - owner-only set_fee(new_fee), set_treasury(new_addr)
  - permissionless sweep() → forwards pending_fees to treasury

Deploy cost: ~125 OCT (matches v1 precedent).
Treasury wallet (Phase 1): octGFAk1bC6sfAqWpX1DcosauQZ7pLy5zqWvZyrbzs8wbbW (same as deploy).
Phase 2: set_treasury(<multisig>). Phase 4: set_treasury(<DAO timelock>).

Usage:
  1. Start signer:   python /Users/mumetnaroq/eschaton/projects/octra/signer/signer_service.py &
  2. Deploy:         python deploy_v2.py --confirm
  3. Verify:         script prints new contract address + tx hash.
"""

import argparse
import json
import socket as sock_mod
import sys
import time
import urllib.request
from pathlib import Path

RPC = "http://46.101.86.250:8080/rpc"
SIGNER_SOCKET = "/tmp/octra_signer.sock"
DEPLOYER = "octGFAk1bC6sfAqWpX1DcosauQZ7pLy5zqWvZyrbzs8wbbW"
V2_SRC = Path(__file__).parent / "8ns-repos" / "8mail-contracts" / "mail_fhe_v2.aml"

DEPLOY_OU = "125000000"  # 125 OCT in OU (1 OCT = 1_000_000 OU; matches v1 cost)

no_proxy = urllib.request.ProxyHandler({})
opener = urllib.request.build_opener(no_proxy)


def rpc(method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode()
    req = urllib.request.Request(RPC, data=payload, headers={"Content-Type": "application/json"})
    with opener.open(req, timeout=30) as resp:
        return json.loads(resp.read())


def get_balance_and_nonce(addr: str) -> tuple[str, int]:
    r = rpc("octra_balance", [addr])
    if "error" in r:
        raise SystemExit(f"RPC error on octra_balance: {r['error']}")
    result = r["result"]
    balance = result.get("balance", "0")
    nonce = max(result.get("nonce", 0), result.get("pending_nonce", 0))
    return balance, nonce


def signer_call(action: str, tx: dict) -> dict:
    s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
    s.connect(SIGNER_SOCKET)
    s.settimeout(60)
    request = json.dumps({"action": action, "tx": tx}).encode()
    s.sendall(len(request).to_bytes(4, "big") + request)

    # recv length-prefixed response
    length_bytes = b""
    while len(length_bytes) < 4:
        chunk = s.recv(4 - len(length_bytes))
        if not chunk:
            break
        length_bytes += chunk
    length = int.from_bytes(length_bytes, "big")
    data = b""
    while len(data) < length:
        chunk = s.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk
    s.close()
    return json.loads(data.decode())


def deploy_v2(dry_run: bool = True):
    # Sanity: source exists, deployer has budget
    if not V2_SRC.exists():
        raise SystemExit(f"Missing v2 source: {V2_SRC}")
    source = V2_SRC.read_text()
    source_hex = source.encode().hex()
    print(f"[v2 source]    {V2_SRC}")
    print(f"[source size]  {len(source)} bytes ({len(source_hex)} hex chars)")

    balance, nonce = get_balance_and_nonce(DEPLOYER)
    print(f"[deployer]     {DEPLOYER}")
    print(f"[balance]      {balance} OU")
    print(f"[next nonce]   {nonce + 1}")

    # Balance is returned in decimal OCT (e.g., "379.960650"). Convert to OU.
    bal_oct = float(balance)
    bal_ou = int(bal_oct * 1_000_000)
    deploy_cost_ou = int(DEPLOY_OU)
    if bal_ou < deploy_cost_ou:
        raise SystemExit(
            f"Insufficient balance: have {bal_oct} OCT ({bal_ou} OU), need {deploy_cost_ou} OU for deploy."
        )

    tx = {
        "from": DEPLOYER,
        "to_": DEPLOYER,  # deploy sends to self
        "amount": "0",
        "nonce": nonce + 1,
        "ou": DEPLOY_OU,
        "timestamp": time.time(),
        "op_type": "deploy",
        "message": source_hex,
    }

    print(f"[op_type]      deploy")
    print(f"[ou (fee)]     {DEPLOY_OU} OU ({int(DEPLOY_OU)/1_000_000:.6f} OCT)")

    if dry_run:
        print("\n[DRY RUN] Pass --confirm to broadcast. Tx envelope:")
        print(json.dumps({k: v for k, v in tx.items() if k != "message"}, indent=2))
        print(f"  message: <{len(source_hex)} hex chars of AML source>")
        return

    print("\n[BROADCAST] signing via oracle & submitting to mainnet …")
    result = signer_call("sign_and_submit", tx)
    rpc_result = result.get("rpc_result", {})
    print("\n[response]")
    print(json.dumps(rpc_result, indent=2))

    if "error" in rpc_result:
        raise SystemExit(f"Deploy failed: {rpc_result['error']}")

    tx_hash = rpc_result.get("result", {}).get("tx_hash") or rpc_result.get("result")
    print(f"\n[tx_hash]      {tx_hash}")
    print("[next steps]")
    print("  1. Wait ~30-60s for finality.")
    print("  2. Query contract address:")
    print(f'     curl -X POST {RPC} -d \'{{"jsonrpc":"2.0","method":"octra_tx","params":["{tx_hash}"],"id":1}}\'')
    print("  3. Update 8mail-cli config with new contract address.")
    print("  4. Run test_fhe_e2e.py against new address to verify fee mechanism.")


def main():
    p = argparse.ArgumentParser(description="Deploy 8mail v2 to Octra mainnet alpha.")
    p.add_argument("--confirm", action="store_true", help="Broadcast tx (omit for dry-run).")
    args = p.parse_args()
    deploy_v2(dry_run=not args.confirm)


if __name__ == "__main__":
    main()
