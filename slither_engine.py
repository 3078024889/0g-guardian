"""
Slither Static Analysis Engine
Wraps Slither to extract structured vulnerability findings from Solidity contracts.
Falls back to bytecode-based heuristics if source code is unavailable.
"""

import os
import json
import tempfile
import asyncio
import subprocess
import logging
from dataclasses import dataclass, asdict
from typing import Optional

log = logging.getLogger("0G-Guardian.Slither")


@dataclass
class Finding:
    id: str
    severity: str          # CRITICAL / HIGH / MEDIUM / LOW / INFO
    category: str          # e.g. "reentrancy", "access-control"
    title: str
    description: str
    affected_functions: list
    source: str            # "slither" | "bytecode_heuristic"
    confidence: str        # HIGH / MEDIUM / LOW
    line_numbers: list


# ─── Severity normalization ──────────────────────────────────────────────────

SLITHER_SEVERITY_MAP = {
    "High": "HIGH",
    "Medium": "MEDIUM",
    "Low": "LOW",
    "Informational": "INFO",
}

# Common critical detector names → map to CRITICAL
CRITICAL_DETECTORS = {
    "reentrancy-eth", "reentrancy-no-eth", "arbitrary-send-eth",
    "controlled-delegatecall", "suicidal", "backdoor",
    "arbitrary-send-erc20", "msg-value-loop",
}


class SlitherEngine:
    def __init__(self):
        self.slither_bin = os.getenv("SLITHER_BIN", "slither")

    async def analyze(
        self,
        contract_address: str,
        source_code: Optional[str],
        bytecode: Optional[str]
    ) -> list[dict]:
        """
        Run static analysis. Returns list of Finding dicts.
        If source_code is available: full Slither analysis.
        If not: bytecode heuristic scan.
        """
        if source_code:
            findings = await self._run_slither(source_code, contract_address)
        else:
            log.warning(f"[{contract_address}] No source code; running bytecode heuristics")
            findings = self._bytecode_heuristics(bytecode or "")

        log.info(f"[{contract_address}] Static analysis complete: {len(findings)} findings")
        return [asdict(f) for f in findings]

    async def _run_slither(self, source_code: str, contract_address: str) -> list[Finding]:
        """Write source to temp file, run Slither, parse JSON output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sol_path = os.path.join(tmpdir, "Target.sol")
            with open(sol_path, "w") as f:
                f.write(source_code)

            cmd = [
                self.slither_bin,
                sol_path,
                "--json", "-",
                "--solc-remaps", "@openzeppelin=node_modules/@openzeppelin",
                "--exclude-dependencies",
                "--no-fail-pedantic",
            ]

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            except asyncio.TimeoutError:
                log.error("Slither timed out")
                return []
            except FileNotFoundError:
                log.error("Slither not found. Install: pip install slither-analyzer")
                return self._demo_findings(contract_address)

            if not stdout:
                log.warning(f"Slither produced no output. stderr: {stderr.decode()[:500]}")
                return self._demo_findings(contract_address)

            try:
                data = json.loads(stdout)
                return self._parse_slither_output(data)
            except json.JSONDecodeError:
                log.error("Could not parse Slither JSON output")
                return []

    def _parse_slither_output(self, data: dict) -> list[Finding]:
        findings = []
        results = data.get("results", {}).get("detectors", [])

        for i, det in enumerate(results):
            detector_name = det.get("check", "unknown")
            raw_severity = det.get("impact", "Low")

            # Upgrade to CRITICAL for known critical detectors
            if detector_name in CRITICAL_DETECTORS:
                severity = "CRITICAL"
            else:
                severity = SLITHER_SEVERITY_MAP.get(raw_severity, "LOW")

            affected = []
            line_numbers = []
            for element in det.get("elements", []):
                if element.get("type") == "function":
                    func_name = element.get("name", "")
                    if func_name:
                        affected.append(func_name)
                src = element.get("source_mapping", {})
                if src.get("lines"):
                    line_numbers.extend(src["lines"])

            findings.append(Finding(
                id=f"SLITHER-{i+1:03d}",
                severity=severity,
                category=detector_name,
                title=f"[{detector_name}] {det.get('description', '')[:80]}",
                description=det.get("description", ""),
                affected_functions=list(set(affected)),
                source="slither",
                confidence=SLITHER_SEVERITY_MAP.get(det.get("confidence", "Low"), "LOW"),
                line_numbers=sorted(set(line_numbers))
            ))

        return findings

    def _bytecode_heuristics(self, bytecode: str) -> list[Finding]:
        """Basic bytecode pattern matching when source is unavailable."""
        findings = []
        bc = bytecode.lower()

        # DELEGATECALL presence (proxy patterns or risky delegatecall)
        if "f4" in bc:  # DELEGATECALL opcode = 0xf4
            findings.append(Finding(
                id="BC-001",
                severity="MEDIUM",
                category="delegatecall-detection",
                title="DELEGATECALL opcode detected",
                description="Contract uses DELEGATECALL. If the callee address is user-controlled, this may allow arbitrary code execution in the context of this contract.",
                affected_functions=[],
                source="bytecode_heuristic",
                confidence="LOW",
                line_numbers=[]
            ))

        # SELFDESTRUCT (0xff)
        if "ff" in bc:
            findings.append(Finding(
                id="BC-002",
                severity="HIGH",
                category="suicidal",
                title="SELFDESTRUCT opcode detected",
                description="Contract can self-destruct. If access controls are insufficient, an attacker could destroy the contract and drain its ETH balance.",
                affected_functions=[],
                source="bytecode_heuristic",
                confidence="MEDIUM",
                line_numbers=[]
            ))

        # No findings from bytecode
        if not findings:
            findings.append(Finding(
                id="BC-000",
                severity="INFO",
                category="bytecode-only",
                title="Source code unavailable — bytecode-only analysis",
                description="Full static analysis requires verified source code. Deploy findings are limited. Recommend verifying source on the block explorer.",
                affected_functions=[],
                source="bytecode_heuristic",
                confidence="LOW",
                line_numbers=[]
            ))

        return findings

    def _demo_findings(self, contract_address: str) -> list[Finding]:
        """Demo/fallback findings when Slither binary is not installed (Wave 1)."""
        return [
            Finding(
                id="DEMO-001",
                severity="INFO",
                category="demo-mode",
                title="Demo mode: Slither not installed in this environment",
                description=f"In production, Slither would run full static analysis on {contract_address}. Install with: pip install slither-analyzer",
                affected_functions=[],
                source="demo",
                confidence="LOW",
                line_numbers=[]
            )
        ]
