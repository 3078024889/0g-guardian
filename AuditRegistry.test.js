const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("AuditRegistry", function () {
  let registry, owner, agent, user;

  const RISK_LEVEL = { UNKNOWN: 0, CRITICAL: 1, HIGH: 2, MEDIUM: 3, LOW: 4, SAFE: 5 };
  const AUDIT_STATUS = { PENDING: 0, IN_PROGRESS: 1, COMPLETED: 2, FAILED: 3 };

  const TARGET_CONTRACT = "0x1234567890123456789012345678901234567890";
  const STORAGE_HASH = ethers.keccak256(ethers.toUtf8Bytes("test-report-hash"));
  const STORAGE_URL = "https://indexer.0g.ai/file/0xabc123";
  const AGENT_VERSION = "0.1.0";

  beforeEach(async function () {
    [owner, agent, user] = await ethers.getSigners();
    const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
    registry = await AuditRegistry.deploy();
    await registry.waitForDeployment();
  });

  // ── Deployment ─────────────────────────────────────────────────────────────

  describe("Deployment", function () {
    it("sets the deployer as owner", async function () {
      expect(await registry.owner()).to.equal(owner.address);
    });

    it("authorizes the deployer as agent", async function () {
      expect(await registry.authorizedAgents(owner.address)).to.be.true;
    });

    it("initializes totalAudits and totalContracts to zero", async function () {
      expect(await registry.totalAudits()).to.equal(0);
      expect(await registry.totalContracts()).to.equal(0);
    });
  });

  // ── Audit Request ──────────────────────────────────────────────────────────

  describe("requestAudit", function () {
    it("emits AuditRequested event with correct args", async function () {
      const tx = await registry.connect(user).requestAudit(TARGET_CONTRACT, "");
      const receipt = await tx.wait();

      const event = receipt.logs.find(
        (log) => log.fragment?.name === "AuditRequested"
      );
      expect(event).to.not.be.undefined;
      expect(event.args.contractAddress.toLowerCase()).to.equal(
        TARGET_CONTRACT.toLowerCase()
      );
      expect(event.args.requester).to.equal(user.address);
    });

    it("stores the audit request with PENDING status", async function () {
      const tx = await registry.connect(user).requestAudit(TARGET_CONTRACT, "0xabc");
      const receipt = await tx.wait();

      const event = receipt.logs.find((l) => l.fragment?.name === "AuditRequested");
      const requestId = event.args.requestId;
      const req = await registry.getAuditRequest(requestId);

      expect(req.contractAddress.toLowerCase()).to.equal(TARGET_CONTRACT.toLowerCase());
      expect(req.requester).to.equal(user.address);
      expect(req.status).to.equal(AUDIT_STATUS.PENDING);
      expect(req.sourceCodeHash).to.equal("0xabc");
    });

    it("reverts for zero address", async function () {
      await expect(
        registry.connect(user).requestAudit(ethers.ZeroAddress, "")
      ).to.be.revertedWithCustomError(registry, "InvalidContractAddress");
    });
  });

  // ── Submit Audit Result ────────────────────────────────────────────────────

  describe("submitAuditResult", function () {
    let requestId;

    beforeEach(async function () {
      // Authorize a separate agent
      await registry.connect(owner).authorizeAgent(agent.address);

      // Create an audit request
      const tx = await registry.connect(user).requestAudit(TARGET_CONTRACT, "");
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "AuditRequested");
      requestId = event.args.requestId;
    });

    it("authorized agent can submit result", async function () {
      await expect(
        registry.connect(agent).submitAuditResult(
          requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
          [0, 2, 1, 3], AGENT_VERSION
        )
      ).to.emit(registry, "AuditCompleted");
    });

    it("stores correct audit record after submission", async function () {
      await registry.connect(agent).submitAuditResult(
        requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
        [0, 2, 1, 3], AGENT_VERSION
      );

      const record = await registry.getAuditRecord(TARGET_CONTRACT);
      expect(record.riskLevel).to.equal(RISK_LEVEL.HIGH);
      expect(record.riskScore).to.equal(75);
      expect(record.storageHash).to.equal(STORAGE_HASH);
      expect(record.storageUrl).to.equal(STORAGE_URL);
      expect(record.highCount).to.equal(2);
      expect(record.mediumCount).to.equal(1);
      expect(record.lowCount).to.equal(3);
      expect(record.agentVersion).to.equal(AGENT_VERSION);
      expect(record.status).to.equal(AUDIT_STATUS.COMPLETED);
    });

    it("increments totalAudits and totalContracts", async function () {
      await registry.connect(agent).submitAuditResult(
        requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
        [0, 2, 1, 3], AGENT_VERSION
      );

      expect(await registry.totalAudits()).to.equal(1);
      expect(await registry.totalContracts()).to.equal(1);
    });

    it("unauthorized account cannot submit result", async function () {
      await expect(
        registry.connect(user).submitAuditResult(
          requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
          [0, 2, 1, 3], AGENT_VERSION
        )
      ).to.be.revertedWithCustomError(registry, "NotAuthorizedAgent");
    });

    it("cannot submit result for non-existent request", async function () {
      const fakeId = ethers.keccak256(ethers.toUtf8Bytes("fake"));
      await expect(
        registry.connect(agent).submitAuditResult(
          fakeId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
          [0, 2, 1, 3], AGENT_VERSION
        )
      ).to.be.revertedWithCustomError(registry, "RequestNotFound");
    });

    it("cannot submit result twice for same request", async function () {
      await registry.connect(agent).submitAuditResult(
        requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
        [0, 2, 1, 3], AGENT_VERSION
      );

      await expect(
        registry.connect(agent).submitAuditResult(
          requestId, RISK_LEVEL.HIGH, 75, STORAGE_HASH, STORAGE_URL,
          [0, 2, 1, 3], AGENT_VERSION
        )
      ).to.be.revertedWithCustomError(registry, "AlreadyCompleted");
    });
  });

  // ── isContractSafe ─────────────────────────────────────────────────────────

  describe("isContractSafe", function () {
    it("returns not audited for unknown contract", async function () {
      const [audited, safe, score] = await registry.isContractSafe(TARGET_CONTRACT);
      expect(audited).to.be.false;
      expect(safe).to.be.false;
      expect(score).to.equal(0);
    });

    it("returns audited + unsafe for contract with critical findings", async function () {
      await registry.connect(owner).authorizeAgent(agent.address);
      const tx = await registry.connect(user).requestAudit(TARGET_CONTRACT, "");
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "AuditRequested");
      const requestId = event.args.requestId;

      await registry.connect(agent).submitAuditResult(
        requestId, RISK_LEVEL.CRITICAL, 95, STORAGE_HASH, STORAGE_URL,
        [2, 1, 0, 0], AGENT_VERSION  // 2 critical, 1 high
      );

      const [audited, safe, score] = await registry.isContractSafe(TARGET_CONTRACT);
      expect(audited).to.be.true;
      expect(safe).to.be.false;
      expect(score).to.equal(95);
    });

    it("returns audited + safe for clean contract", async function () {
      await registry.connect(owner).authorizeAgent(agent.address);
      const tx = await registry.connect(user).requestAudit(TARGET_CONTRACT, "");
      const receipt = await tx.wait();
      const event = receipt.logs.find((l) => l.fragment?.name === "AuditRequested");
      const requestId = event.args.requestId;

      await registry.connect(agent).submitAuditResult(
        requestId, RISK_LEVEL.SAFE, 5, STORAGE_HASH, STORAGE_URL,
        [0, 0, 1, 2], AGENT_VERSION  // No critical or high
      );

      const [audited, safe, score] = await registry.isContractSafe(TARGET_CONTRACT);
      expect(audited).to.be.true;
      expect(safe).to.be.true;
      expect(score).to.equal(5);
    });
  });

  // ── Access Control ─────────────────────────────────────────────────────────

  describe("Access Control", function () {
    it("owner can authorize a new agent", async function () {
      await expect(registry.connect(owner).authorizeAgent(agent.address))
        .to.emit(registry, "AgentAuthorized")
        .withArgs(agent.address);
      expect(await registry.authorizedAgents(agent.address)).to.be.true;
    });

    it("owner can revoke an agent", async function () {
      await registry.connect(owner).authorizeAgent(agent.address);
      await expect(registry.connect(owner).revokeAgent(agent.address))
        .to.emit(registry, "AgentRevoked")
        .withArgs(agent.address);
      expect(await registry.authorizedAgents(agent.address)).to.be.false;
    });

    it("non-owner cannot authorize agents", async function () {
      await expect(
        registry.connect(user).authorizeAgent(agent.address)
      ).to.be.revertedWithCustomError(registry, "NotOwner");
    });

    it("owner can transfer ownership", async function () {
      await registry.connect(owner).transferOwnership(user.address);
      expect(await registry.owner()).to.equal(user.address);
    });
  });
});
