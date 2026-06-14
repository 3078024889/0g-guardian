# 0G Guardian — Onchain AI Security Audit Agent

> An autonomous AI agent that audits smart contracts, stores tamper-proof audit reports on 0G Storage, and publishes verifiable risk scores on 0G Chain.

[![0G Chain](https://img.shields.io/badge/0G-Chain-blue)](https://0g.ai)
[![0G Compute](https://img.shields.io/badge/0G-Compute-green)](https://pc.0g.ai)
[![0G Storage](https://img.shields.io/badge/0G-Storage-orange)](https://docs.0g.ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Overview

**0G Guardian** is a fully autonomous, onchain AI security agent for smart contracts. It combines static vulnerability analysis with LLM-powered semantic reasoning — all running through 0G's decentralized infrastructure — to make professional-grade smart contract auditing accessible, affordable, and verifiable.

**The problem it solves:**  
Smart contract audits today cost $20,000–$100,000, take weeks, and produce off-chain PDFs that can be altered or faked. 87% of hacked protocols in 2025 had never been formally audited. 0G Guardian makes security analysis instant, on-demand, and provably immutable.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   User / dApp Interface                  │
└───────────────────────┬─────────────────────────────────┘
                        │  Submit contract address / source
                        ▼
┌─────────────────────────────────────────────────────────┐
│              AuditRegistry.sol (0G Chain)                │
│   Emits AuditRequested event → stores final AuditRecord  │
└───────────────────────┬─────────────────────────────────┘
                        │  Event listener (agent)
                        ▼
┌─────────────────────────────────────────────────────────┐
│                  Guardian Agent (Python)                  │
│                                                          │
│  ┌──────────────────┐    ┌───────────────────────────┐  │
│  │  Slither Engine  │    │  0G Compute: LLM Inference │  │
│  │  (static rules)  │    │  (semantic vuln reasoning) │  │
│  └────────┬─────────┘    └─────────────┬─────────────┘  │
│           └──────────────┬─────────────┘                 │
│                          ▼                               │
│              Report Generator (JSON)                     │
└──────────────────────────┬──────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
┌─────────────────────┐    ┌──────────────────────────────┐
│   0G Storage SDK    │    │  AuditRegistry.sol (0G Chain) │
│  Upload full report │    │  Write: riskScore + hash +    │
│  Return merkle hash │    │  timestamp (immutable record) │
└─────────────────────┘    └──────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│              Frontend: Search & Display                  │
│   Input contract addr → view risk score + full report   │
└─────────────────────────────────────────────────────────┘
```

---

## 0G Components Used

| Component | Role |
|---|---|
| **0G Chain** | Smart contract registry (`AuditRegistry.sol`) — immutable on-chain audit records |
| **0G Compute** | LLM-powered AI inference for semantic vulnerability reasoning |
| **0G Storage** | Decentralized storage for full JSON audit reports (censorship-resistant, permanent) |
| **0G Pay** | Pay-per-audit billing — agents transact autonomously using $0G tokens |

---

## Why 0G?

| Need | Solution on 0G |
|---|---|
| AI inference without AWS lock-in | 0G Compute: decentralized GPU network, verifiable results |
| Store large audit reports | 0G Storage: petabyte-scale, content-addressed, cheap |
| Immutable public record | 0G Chain: EVM-compatible, fast finality, queryable forever |
| Agent-native payments | 0G Pay: autonomous billing without centralized subscriptions |

---

## Project Structure

```
0g-guardian/
├── contracts/
│   └── AuditRegistry.sol       # On-chain audit record registry
├── agent/
│   ├── guardian_agent.py       # Core autonomous agent loop
│   ├── slither_engine.py       # Static analysis wrapper
│   ├── llm_engine.py           # 0G Compute LLM integration
│   ├── storage_client.py       # 0G Storage SDK integration
│   └── report_generator.py     # JSON report builder
├── frontend/
│   └── src/
│       └── App.jsx             # React frontend (search + display)
├── scripts/
│   ├── deploy.js               # Hardhat deployment script
│   └── test_full_flow.py       # End-to-end integration test
├── test/
│   └── AuditRegistry.test.js   # Contract unit tests
├── docs/
│   └── architecture.md         # Extended technical documentation
├── hardhat.config.js
├── package.json
├── requirements.txt
└── README.md
```

---

## Quickstart

### Prerequisites

```bash
node >= 18
python >= 3.10
pip install slither-analyzer
```

### 1. Install dependencies

```bash
# Solidity / Hardhat
npm install

# Python agent
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in:
# PRIVATE_KEY=your_wallet_private_key
# OG_CHAIN_RPC=https://evmrpc-testnet.0g.ai
# OG_STORAGE_RPC=https://rpc-storage-testnet.0g.ai
# OG_COMPUTE_ENDPOINT=https://inference.0g.ai
```

### 3. Deploy contract to 0G Testnet

```bash
npx hardhat run scripts/deploy.js --network og_testnet
```

### 4. Run the Guardian Agent

```bash
python agent/guardian_agent.py
```

### 5. Submit an audit request

```bash
python scripts/test_full_flow.py --contract 0xYourContractAddress
```

---

## Wave Roadmap

| Wave | Target | Deliverable |
|---|---|---|
| **Wave 1** | Architecture + 0G Integration Plan | This repo, full design docs, contract skeleton |
| **Wave 2** | Testnet Prototype | Slither + 0G Storage live, basic frontend |
| **Wave 3** | Mainnet Deployment | AuditRegistry on 0G mainnet, 0G Compute AI live |
| **Wave 4** | User Acquisition | 3+ protocol partners, 50+ audits, retention data |
| **Wave 5** | Demo Day | Full demo, cost savings data, paid integrations |

---

## Team

Building at the intersection of AI security research and decentralized infrastructure. Background in smart contract auditing, Python automation, and Web3 protocol development.

---

## License

MIT
