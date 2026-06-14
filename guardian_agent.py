"""
0G Guardian — Core Autonomous Agent
Listens for AuditRequested events on 0G Chain, runs analysis pipeline,
stores results on 0G Storage, and writes final record back to 0G Chain.
"""

import os
import json
import time
import asyncio
import logging
from datetime import datetime
from web3 import Web3
from dotenv import load_dotenv

from slither_engine import SlitherEngine
from llm_engine import LLMEngine
from storage_client import ZeroGStorageClient
from report_generator import ReportGenerator

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("0G-Guardian")

AGENT_VERSION = "0.1.0"

# ─── ABI (minimal — only events + functions we need) ─────────────────────────

REGISTRY_ABI = json.loads("""[
  {
    "name": "AuditRequested",
    "type": "event",
    "inputs": [
      {"name": "requestId", "type": "bytes32", "indexed": true},
      {"name": "contractAddress", "type": "address", "indexed": true},
      {"name": "requester", "type": "address", "indexed": true},
      {"name": "timestamp", "type": "uint256", "indexed": false}
    ]
  },
  {
    "name": "submitAuditResult",
    "type": "function",
    "inputs": [
      {"name": "requestId", "type": "bytes32"},
      {"name": "riskLevel", "type": "uint8"},
      {"name": "riskScore", "type": "uint8"},
      {"name": "storageHash", "type": "bytes32"},
      {"name": "storageUrl", "type": "string"},
      {"name": "counts", "type": "uint32[4]"},
      {"name": "agentVersion", "type": "string"}
    ],
    "outputs": [],
    "stateMutability": "nonpayable"
  },
  {
    "name": "getAuditRequest",
    "type": "function",
    "inputs": [{"name": "requestId", "type": "bytes32"}],
    "outputs": [
      {
        "name": "",
        "type": "tuple",
        "components": [
          {"name": "contractAddress", "type": "address"},
          {"name": "requester", "type": "address"},
          {"name": "requestTimestamp", "type": "uint256"},
          {"name": "status", "type": "uint8"},
          {"name": "sourceCodeHash", "type": "string"}
        ]
      }
    ],
    "stateMutability": "view"
  }
]""")

RISK_LEVEL_MAP = {
    "SAFE": 5,
    "LOW": 4,
    "MEDIUM": 3,
    "HIGH": 2,
    "CRITICAL": 1,
    "UNKNOWN": 0
}


class GuardianAgent:
    def __init__(self):
        self.rpc_url = os.getenv("OG_CHAIN_RPC", "https://evmrpc-testnet.0g.ai")
        self.registry_address = os.getenv("REGISTRY_ADDRESS", "")
        self.private_key = os.getenv("PRIVATE_KEY", "")
        self.poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))

        # Web3 setup
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        self.account = self.w3.eth.account.from_key(self.private_key)
        log.info(f"Agent wallet: {self.account.address}")

        if not self.registry_address:
            raise ValueError("REGISTRY_ADDRESS not set in .env")

        self.registry = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.registry_address),
            abi=REGISTRY_ABI
        )

        # Sub-engines
        self.slither = SlitherEngine()
        self.llm = LLMEngine()
        self.storage = ZeroGStorageClient()
        self.reporter = ReportGenerator()

        self.last_block = self.w3.eth.block_number
        log.info(f"Starting from block {self.last_block}")

    async def run(self):
        """Main event loop — polls for new AuditRequested events."""
        log.info("0G Guardian Agent started. Listening for audit requests...")
        while True:
            try:
                await self.poll_events()
            except Exception as e:
                log.error(f"Poll error: {e}", exc_info=True)
            await asyncio.sleep(self.poll_interval)

    async def poll_events(self):
        current_block = self.w3.eth.block_number
        if current_block <= self.last_block:
            return

        log.info(f"Scanning blocks {self.last_block + 1} → {current_block}")

        events = self.registry.events.AuditRequested.get_logs(
            from_block=self.last_block + 1,
            to_block=current_block
        )

        for event in events:
            request_id = event["args"]["requestId"]
            contract_address = event["args"]["contractAddress"]
            log.info(f"New audit request: {request_id.hex()} for {contract_address}")
            await self.process_audit(request_id, contract_address)

        self.last_block = current_block

    async def process_audit(self, request_id: bytes, contract_address: str):
        """Full audit pipeline for a single contract."""
        start_time = time.time()
        log.info(f"[{contract_address}] Starting audit pipeline...")

        try:
            # ── Step 1: Fetch contract bytecode / source ───────────────────────
            log.info(f"[{contract_address}] Fetching contract code...")
            bytecode = self.w3.eth.get_code(Web3.to_checksum_address(contract_address))
            source_code = await self._try_fetch_source(contract_address)

            # ── Step 2: Static analysis via Slither ───────────────────────────
            log.info(f"[{contract_address}] Running Slither static analysis...")
            static_findings = await self.slither.analyze(
                contract_address=contract_address,
                source_code=source_code,
                bytecode=bytecode.hex()
            )
            log.info(f"[{contract_address}] Static findings: {len(static_findings)}")

            # ── Step 3: AI semantic analysis via 0G Compute ───────────────────
            log.info(f"[{contract_address}] Running LLM semantic analysis via 0G Compute...")
            ai_findings = await self.llm.analyze(
                contract_address=contract_address,
                source_code=source_code,
                static_findings=static_findings
            )
            log.info(f"[{contract_address}] AI findings: {len(ai_findings)}")

            # ── Step 4: Generate unified report ───────────────────────────────
            log.info(f"[{contract_address}] Generating audit report...")
            report = self.reporter.generate(
                contract_address=contract_address,
                static_findings=static_findings,
                ai_findings=ai_findings,
                duration_seconds=time.time() - start_time,
                agent_version=AGENT_VERSION
            )

            # ── Step 5: Upload report to 0G Storage ───────────────────────────
            log.info(f"[{contract_address}] Uploading report to 0G Storage...")
            storage_result = await self.storage.upload(
                data=json.dumps(report, indent=2).encode("utf-8"),
                filename=f"audit_{contract_address}_{int(time.time())}.json"
            )
            log.info(f"[{contract_address}] Stored: {storage_result['hash']}")

            # ── Step 6: Write result to 0G Chain ──────────────────────────────
            log.info(f"[{contract_address}] Writing result to 0G Chain...")
            tx_hash = await self.submit_result(
                request_id=request_id,
                report=report,
                storage_result=storage_result
            )
            log.info(f"[{contract_address}] ✅ Audit complete. Tx: {tx_hash}")

        except Exception as e:
            log.error(f"[{contract_address}] Audit failed: {e}", exc_info=True)

    async def submit_result(self, request_id: bytes, report: dict, storage_result: dict) -> str:
        """Submit audit result transaction to AuditRegistry on 0G Chain."""
        summary = report["summary"]
        risk_level = RISK_LEVEL_MAP.get(summary["overall_risk"], 0)
        risk_score = summary["risk_score"]

        counts = [
            summary["findings_by_severity"].get("CRITICAL", 0),
            summary["findings_by_severity"].get("HIGH", 0),
            summary["findings_by_severity"].get("MEDIUM", 0),
            summary["findings_by_severity"].get("LOW", 0),
        ]

        storage_hash = bytes.fromhex(
            storage_result["hash"].replace("0x", "").ljust(64, "0")
        )

        nonce = self.w3.eth.get_transaction_count(self.account.address)
        gas_price = self.w3.eth.gas_price

        tx = self.registry.functions.submitAuditResult(
            request_id,
            risk_level,
            risk_score,
            storage_hash,
            storage_result["url"],
            counts,
            AGENT_VERSION
        ).build_transaction({
            "from": self.account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 300000,
        })

        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt["status"] != 1:
            raise RuntimeError(f"Transaction reverted: {tx_hash.hex()}")

        return tx_hash.hex()

    async def _try_fetch_source(self, contract_address: str) -> str | None:
        """Attempt to fetch verified source code from block explorer."""
        try:
            import aiohttp
            explorer_api = os.getenv(
                "EXPLORER_API",
                f"https://chainscan-galileo.0g.ai/api?module=contract&action=getsourcecode&address={contract_address}"
            )
            async with aiohttp.ClientSession() as session:
                async with session.get(explorer_api, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if data.get("status") == "1" and data["result"][0].get("SourceCode"):
                        return data["result"][0]["SourceCode"]
        except Exception:
            pass
        return None


if __name__ == "__main__":
    agent = GuardianAgent()
    asyncio.run(agent.run())
