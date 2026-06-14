"""
0G Guardian — End-to-End Integration Test
Tests the full pipeline: request audit → agent processes → result on-chain.
Run: python scripts/test_full_flow.py --contract 0xYourContractAddress
"""

import os
import sys
import json
import time
import asyncio
import argparse
import logging
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("0G-Guardian.Test")

# Sample vulnerable contract source for local testing
SAMPLE_VULNERABLE_CONTRACT = """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// ⚠️  INTENTIONALLY VULNERABLE CONTRACT FOR TESTING PURPOSES ONLY
contract VulnerableBank {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    // VULNERABILITY: Classic reentrancy — state updated AFTER external call
    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        // Bug: sends ETH before updating balance
        (bool success, ) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        balances[msg.sender] -= amount;  // Should be BEFORE the call
    }

    // VULNERABILITY: Anyone can drain the contract
    function emergencyWithdraw() external {
        payable(msg.sender).transfer(address(this).balance);
    }
}
"""

REGISTRY_ABI = json.loads("""[
  {
    "name": "requestAudit",
    "type": "function",
    "inputs": [
      {"name": "contractAddress", "type": "address"},
      {"name": "sourceCodeHash", "type": "string"}
    ],
    "outputs": [{"name": "requestId", "type": "bytes32"}],
    "stateMutability": "nonpayable"
  },
  {
    "name": "getAuditRecord",
    "type": "function",
    "inputs": [{"name": "contractAddress", "type": "address"}],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "components": [
          {"name": "contractAddress", "type": "address"},
          {"name": "requester", "type": "address"},
          {"name": "timestamp", "type": "uint256"},
          {"name": "riskLevel", "type": "uint8"},
          {"name": "riskScore", "type": "uint8"},
          {"name": "storageHash", "type": "bytes32"},
          {"name": "storageUrl", "type": "string"},
          {"name": "criticalCount", "type": "uint32"},
          {"name": "highCount", "type": "uint32"},
          {"name": "mediumCount", "type": "uint32"},
          {"name": "lowCount", "type": "uint32"},
          {"name": "status", "type": "uint8"},
          {"name": "agentVersion", "type": "string"}
        ]
      }
    ],
    "stateMutability": "view"
  },
  {
    "name": "isContractSafe",
    "type": "function",
    "inputs": [{"name": "contractAddress", "type": "address"}],
    "outputs": [
      {"name": "audited", "type": "bool"},
      {"name": "safe", "type": "bool"},
      {"name": "score", "type": "uint8"}
    ],
    "stateMutability": "view"
  },
  {
    "name": "AuditRequested",
    "type": "event",
    "inputs": [
      {"name": "requestId", "type": "bytes32", "indexed": true},
      {"name": "contractAddress", "type": "address", "indexed": true},
      {"name": "requester", "type": "address", "indexed": true},
      {"name": "timestamp", "type": "uint256", "indexed": false}
    ]
  }
]""")

RISK_LEVEL_NAMES = {0: "UNKNOWN", 1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "SAFE"}


async def run_local_pipeline_test():
    """Run the full analysis pipeline locally without deploying to chain."""
    log.info("=" * 60)
    log.info("  0G Guardian — Local Pipeline Test")
    log.info("=" * 60)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))
    from slither_engine import SlitherEngine
    from llm_engine import LLMEngine
    from storage_client import ZeroGStorageClient
    from report_generator import ReportGenerator

    contract_address = "0x1234567890123456789012345678901234567890"

    log.info("\n[1/5] Running Slither static analysis...")
    slither = SlitherEngine()
    static_findings = await slither.analyze(
        contract_address=contract_address,
        source_code=SAMPLE_VULNERABLE_CONTRACT,
        bytecode=None
    )
    log.info(f"      → {len(static_findings)} findings")
    for f in static_findings:
        log.info(f"        [{f['severity']}] {f['title'][:60]}")

    log.info("\n[2/5] Running LLM semantic analysis via 0G Compute...")
    llm = LLMEngine()
    ai_findings = await llm.analyze(
        contract_address=contract_address,
        source_code=SAMPLE_VULNERABLE_CONTRACT,
        static_findings=static_findings
    )
    log.info(f"      → {len(ai_findings)} additional findings")
    for f in ai_findings:
        log.info(f"        [{f['severity']}] {f['title'][:60]}")

    log.info("\n[3/5] Generating unified audit report...")
    reporter = ReportGenerator()
    report = reporter.generate(
        contract_address=contract_address,
        static_findings=static_findings,
        ai_findings=ai_findings,
        duration_seconds=15.0,
        agent_version="0.1.0-test"
    )
    log.info(f"      → Overall risk: {report['summary']['overall_risk']}")
    log.info(f"      → Risk score: {report['summary']['risk_score']}/100")
    log.info(f"      → Total findings: {report['summary']['total_findings']}")

    log.info("\n[4/5] Uploading report to 0G Storage...")
    storage = ZeroGStorageClient()
    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    storage_result = await storage.upload(
        data=report_bytes,
        filename=f"audit_{contract_address}_test.json"
    )
    log.info(f"      → Hash: {storage_result['hash']}")
    log.info(f"      → URL:  {storage_result['url']}")

    log.info("\n[5/5] Saving report locally...")
    os.makedirs("reports", exist_ok=True)
    report_path = f"reports/test_audit_{int(time.time())}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"      → Saved to: {report_path}")

    log.info("\n" + "=" * 60)
    log.info("  ✅ Local pipeline test PASSED")
    log.info("=" * 60)
    log.info(f"\n  Risk Level:   {report['summary']['overall_risk']}")
    log.info(f"  Risk Score:   {report['summary']['risk_score']}/100")
    log.info(f"  Findings:     {report['summary']['total_findings']}")
    log.info(f"  Critical:     {report['summary']['findings_by_severity']['CRITICAL']}")
    log.info(f"  High:         {report['summary']['findings_by_severity']['HIGH']}")
    log.info(f"  Medium:       {report['summary']['findings_by_severity']['MEDIUM']}")
    log.info(f"  Storage Hash: {storage_result['hash']}")
    log.info("\n  Full report: " + report_path)

    return report


async def run_chain_test(contract_address: str):
    """Submit a real audit request to the deployed contract on 0G Chain."""
    rpc_url = os.getenv("OG_CHAIN_RPC", "https://evmrpc-testnet.0g.ai")
    registry_address = os.getenv("REGISTRY_ADDRESS")
    private_key = os.getenv("PRIVATE_KEY")

    if not registry_address:
        log.error("REGISTRY_ADDRESS not set in .env")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    account = w3.eth.account.from_key(private_key)
    registry = w3.eth.contract(
        address=Web3.to_checksum_address(registry_address),
        abi=REGISTRY_ABI
    )

    log.info(f"Requesting audit for: {contract_address}")
    log.info(f"Registry: {registry_address}")
    log.info(f"Wallet: {account.address}")

    # Submit audit request transaction
    nonce = w3.eth.get_transaction_count(account.address)
    tx = registry.functions.requestAudit(
        Web3.to_checksum_address(contract_address),
        ""  # no source hash for this test
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gasPrice": w3.eth.gas_price,
        "gas": 200000,
    })

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    log.info(f"✅ Audit request submitted. Tx: {tx_hash.hex()}")
    log.info(f"   Block: {receipt['blockNumber']}")
    log.info(f"   Gas used: {receipt['gasUsed']}")
    log.info(f"\nNow run the Guardian Agent to process this request:")
    log.info(f"   python agent/guardian_agent.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="0G Guardian Integration Test")
    parser.add_argument(
        "--contract", type=str, default=None,
        help="Contract address to audit (if not provided, runs local pipeline test)"
    )
    parser.add_argument(
        "--local-only", action="store_true",
        help="Run local pipeline test without chain interaction"
    )
    args = parser.parse_args()

    if args.contract and not args.local_only:
        asyncio.run(run_chain_test(args.contract))
    else:
        asyncio.run(run_local_pipeline_test())
