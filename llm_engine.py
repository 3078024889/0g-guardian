"""
LLM Engine — 0G Compute Network Integration
Sends contract source + static findings to an LLM via 0G Compute for
semantic vulnerability reasoning (business logic, access control, economic attacks).
"""

import os
import json
import aiohttp
import logging
from typing import Optional

log = logging.getLogger("0G-Guardian.LLM")

OG_COMPUTE_ENDPOINT = os.getenv("OG_COMPUTE_ENDPOINT", "https://inference.0g.ai")
OG_COMPUTE_MODEL = os.getenv("OG_COMPUTE_MODEL", "Qwen/Qwen2.5-72B-Instruct")
OG_COMPUTE_API_KEY = os.getenv("OG_COMPUTE_API_KEY", "")

SYSTEM_PROMPT = """You are an expert smart contract security auditor.
Your task is to analyze Solidity smart contracts and identify vulnerabilities
that static analysis tools may miss — particularly logic errors, economic attacks,
governance manipulation, and business-logic flaws.

For each vulnerability you find, respond ONLY with a valid JSON array. Each item:
{
  "id": "AI-001",
  "severity": "CRITICAL|HIGH|MEDIUM|LOW|INFO",
  "category": "short-category-name",
  "title": "Brief vulnerability title",
  "description": "Detailed explanation of the vulnerability",
  "attack_vector": "How an attacker would exploit this",
  "affected_functions": ["functionName1", "functionName2"],
  "recommendation": "How to fix this vulnerability",
  "confidence": "HIGH|MEDIUM|LOW"
}

If no additional vulnerabilities are found beyond static analysis, return: []
Return ONLY valid JSON, no markdown, no explanation outside the JSON."""


class LLMEngine:
    def __init__(self):
        self.endpoint = OG_COMPUTE_ENDPOINT
        self.model = OG_COMPUTE_MODEL
        self.api_key = OG_COMPUTE_API_KEY
        self.timeout = aiohttp.ClientTimeout(total=120)

    async def analyze(
        self,
        contract_address: str,
        source_code: Optional[str],
        static_findings: list[dict]
    ) -> list[dict]:
        """
        Run LLM semantic analysis via 0G Compute Network.
        Returns list of AI-identified finding dicts.
        """
        if not source_code:
            log.warning(f"[{contract_address}] No source code for LLM analysis")
            return []

        prompt = self._build_prompt(contract_address, source_code, static_findings)

        try:
            findings = await self._call_0g_compute(prompt)
            log.info(f"[{contract_address}] LLM found {len(findings)} additional issues")
            return findings
        except Exception as e:
            log.error(f"[{contract_address}] LLM analysis failed: {e}")
            return []

    def _build_prompt(
        self,
        contract_address: str,
        source_code: str,
        static_findings: list[dict]
    ) -> str:
        # Truncate source to ~6000 chars to stay within context limits
        truncated_source = source_code[:6000]
        if len(source_code) > 6000:
            truncated_source += "\n\n[... source truncated for context limit ...]"

        static_summary = json.dumps(
            [{"severity": f["severity"], "category": f["category"], "title": f["title"]}
             for f in static_findings[:20]],
            indent=2
        )

        return f"""Analyze this smart contract for security vulnerabilities.

CONTRACT ADDRESS: {contract_address}

SOURCE CODE:
```solidity
{truncated_source}
```

STATIC ANALYSIS ALREADY FOUND THESE ISSUES (do not duplicate them):
{static_summary}

Find ADDITIONAL vulnerabilities the static analysis missed, especially:
1. Business logic flaws
2. Economic / flashloan attack vectors
3. Access control issues
4. Reentrancy patterns not caught by static tools
5. Oracle manipulation risks
6. Governance attack vectors
7. Integer overflow/underflow edge cases
8. Front-running vulnerabilities
9. Denial of service vectors
10. Unsafe external calls

Respond with JSON array only."""

    async def _call_0g_compute(self, prompt: str) -> list[dict]:
        """
        Call 0G Compute Network's OpenAI-compatible inference endpoint.
        0G Compute uses an OpenAI-compatible API, so we use /v1/chat/completions.
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,   # Low temperature for consistent security analysis
            "max_tokens": 2048,
            "stream": False
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                f"{self.endpoint}/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"0G Compute API error {resp.status}: {error_text[:500]}")

                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()

                # Strip markdown code fences if present
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]

                findings = json.loads(content)

                # Normalize and validate each finding
                validated = []
                for i, f in enumerate(findings):
                    if not isinstance(f, dict):
                        continue
                    validated.append({
                        "id": f.get("id", f"AI-{i+1:03d}"),
                        "severity": f.get("severity", "MEDIUM").upper(),
                        "category": f.get("category", "ai-analysis"),
                        "title": f.get("title", "Unnamed finding"),
                        "description": f.get("description", ""),
                        "attack_vector": f.get("attack_vector", ""),
                        "affected_functions": f.get("affected_functions", []),
                        "recommendation": f.get("recommendation", ""),
                        "confidence": f.get("confidence", "MEDIUM").upper(),
                        "source": "llm_0g_compute",
                        "model": self.model,
                    })

                return validated
