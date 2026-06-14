# 0G Guardian — Architecture Documentation

## System Overview

0G Guardian is a three-layer autonomous system built entirely on 0G's decentralized infrastructure.

---

## Layer 1: On-Chain Registry (0G Chain)

### AuditRegistry.sol

The smart contract serves as the **immutable source of truth** for all audit records.

```
User/dApp
    │
    ▼  requestAudit(contractAddress)
AuditRegistry.sol
    │  emit AuditRequested(requestId, contractAddress, requester)
    │
    ▼  (after agent completes work)
    │  submitAuditResult(requestId, riskLevel, riskScore, storageHash, ...)
    │
    ▼  store AuditRecord → mapping(address => AuditRecord)
    │
    ▼  isContractSafe(contractAddress) → (audited, safe, score)
```

**Key design decisions:**
- Only content hash stored on-chain (not full report) → gas efficient
- Public `isContractSafe()` → composable with any DeFi protocol
- Authorized agent model → prevents spam submissions
- Full audit history preserved → `auditHistory[address][]`

---

## Layer 2: Guardian Agent (Python Async)

### Event-Driven Architecture

```
┌─────────────────────────────────────────────────────┐
│                  guardian_agent.py                   │
│                                                      │
│  while True:                                         │
│    poll 0G Chain for AuditRequested events           │
│    for each new event:                               │
│      asyncio.create_task(process_audit(...))         │
│    sleep(POLL_INTERVAL_SECONDS)                      │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   SlitherEngine   LLMEngine   StorageClient
```

**Why async?**
- Multiple audits can run concurrently without blocking
- 0G Compute inference is I/O bound (network call) — async is ideal
- Agent can process a new request every ~15s while others are in-flight

---

## Layer 3: Analysis Pipeline

### Step-by-Step Execution

```
1. FETCH
   ├── Bytecode: w3.eth.get_code(address)
   └── Source:   block explorer API (if verified)

2. STATIC ANALYSIS (SlitherEngine)
   ├── Write source to temp file
   ├── Run: slither Target.sol --json -
   ├── Parse detector results
   └── Normalize to Finding structs
       Fields: id, severity, category, title, description,
               affected_functions, confidence, line_numbers

3. AI SEMANTIC ANALYSIS (LLMEngine → 0G Compute)
   ├── Build prompt: source + static findings summary
   ├── POST /v1/chat/completions (OpenAI-compatible)
   │   Model: Qwen/Qwen2.5-72B-Instruct
   │   Temp: 0.1 (deterministic security analysis)
   └── Parse JSON response → normalize to Finding structs
       Additional fields: attack_vector, recommendation

4. REPORT GENERATION (ReportGenerator)
   ├── Merge: static_findings + ai_findings
   ├── Deduplicate by (category, severity)
   ├── Score: Σ severity_weights (CRITICAL=40, HIGH=20, MEDIUM=8, LOW=2)
   ├── Cap at 100
   └── Output: structured JSON report (schema v1.0)

5. STORAGE (ZeroGStorageClient → 0G Storage)
   ├── Serialize report to JSON bytes
   ├── POST to 0G Storage RPC: zgs_uploadFile
   └── Return: { hash, url, size }

6. ON-CHAIN WRITE (guardian_agent.py → 0G Chain)
   ├── Build tx: submitAuditResult(requestId, riskLevel, riskScore,
   │                               storageHash, storageUrl, counts, version)
   ├── Sign with agent wallet
   ├── Send to 0G Chain
   └── Wait for receipt (timeout: 120s)
```

---

## Risk Scoring Model

| Severity | Points per finding | Notes |
|---|---|---|
| CRITICAL | 40 | Reentrancy, arbitrary send, suicidal |
| HIGH | 20 | Access control, unsafe delegatecall |
| MEDIUM | 8 | Logic flaws, oracle issues |
| LOW | 2 | Minor issues, gas inefficiency |
| INFO | 0 | Informational only |

**Score = min(Σ points, 100)**

**Risk Level mapping:**
- Score 0, no CRITICAL/HIGH → `SAFE`
- Any LOW finding → `LOW`
- Any MEDIUM finding → `MEDIUM`
- Any HIGH finding → `HIGH`
- Any CRITICAL finding → `CRITICAL`

---

## 0G Integration Details

### 0G Chain
- **Network**: Galileo Testnet (ChainID 16601) → Mainnet (ChainID 16600)
- **RPC**: `https://evmrpc-testnet.0g.ai`
- **Contract**: `AuditRegistry.sol` — EVM-compatible, Solidity 0.8.20
- **Gas**: ~150,000–300,000 per `submitAuditResult` call

### 0G Compute
- **Endpoint**: `https://inference.0g.ai/v1/chat/completions`
- **API**: OpenAI-compatible (drop-in replacement)
- **Model**: `Qwen/Qwen2.5-72B-Instruct`
- **Auth**: Bearer token via `OG_COMPUTE_API_KEY`
- **Typical latency**: 15–45s for contract analysis

### 0G Storage
- **RPC**: `https://rpc-storage-testnet.0g.ai`
- **Indexer**: `https://indexer-storage-testnet-standard.0g.ai`
- **Method**: `zgs_uploadFile` (JSON-RPC)
- **Report size**: typically 20KB–200KB per audit
- **Retrieval**: `{indexer_url}/file/{content_hash}`

---

## Security Model

### Agent Authorization
- Only wallets in `authorizedAgents` mapping can submit results
- Owner controls agent authorization
- Prevents malicious actors from submitting fake audit results

### Report Integrity
- Full report stored on 0G Storage (content-addressed)
- Content hash stored on 0G Chain
- Anyone can verify: download report, hash it, compare to on-chain hash
- Tamper-evident by construction

### Composability
```solidity
// Any DeFi protocol can integrate:
(bool audited, bool safe, uint8 score) = auditRegistry.isContractSafe(target);
require(audited && safe, "Contract not audited or has critical issues");
```

---

## Future Architecture (Wave 4–5)

```
                    ┌─────────────────────┐
                    │   Agentic ID        │
                    │   (ERC-7857)        │
                    │   Guardian Agent    │
                    │   tokenized on 0G   │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
   DeFi Sub-Agent      NFT Sub-Agent      Gov Sub-Agent
   (flash loan,        (royalty, mint     (proposal,
    oracle attacks)     manipulation)      timelock bypass)
```

Multi-agent architecture with specialized sub-agents, each tokenized as Agentic IDs, forming a verifiable AI security network on 0G.
