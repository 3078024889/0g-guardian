// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title AuditRegistry
 * @author 0G Guardian Team
 * @notice Immutable on-chain registry of AI-powered smart contract audits.
 *         Audit reports are stored on 0G Storage; only the content hash and
 *         risk metadata are stored on-chain for efficiency.
 */
contract AuditRegistry {

    // ─── Enums ────────────────────────────────────────────────────────────────

    enum RiskLevel { UNKNOWN, CRITICAL, HIGH, MEDIUM, LOW, SAFE }
    enum AuditStatus { PENDING, IN_PROGRESS, COMPLETED, FAILED }

    // ─── Structs ──────────────────────────────────────────────────────────────

    struct AuditRecord {
        address contractAddress;   // Audited contract
        address requester;         // Who requested the audit
        uint256 timestamp;         // Block timestamp of completion
        RiskLevel riskLevel;       // AI-assigned overall risk
        uint8 riskScore;           // 0–100 numeric score (0=safe, 100=critical)
        bytes32 storageHash;       // 0G Storage content hash of full report
        string storageUrl;         // 0G Storage retrieval URL
        uint32 criticalCount;      // Number of critical findings
        uint32 highCount;
        uint32 mediumCount;
        uint32 lowCount;
        AuditStatus status;
        string agentVersion;       // Guardian agent version that ran the audit
    }

    struct AuditRequest {
        address contractAddress;
        address requester;
        uint256 requestTimestamp;
        AuditStatus status;
        string sourceCodeHash;     // Optional: keccak of submitted source
    }

    // ─── State ────────────────────────────────────────────────────────────────

    /// @notice Latest audit record per contract address
    mapping(address => AuditRecord) public auditRecords;

    /// @notice Full audit history per contract (multiple audits over time)
    mapping(address => AuditRecord[]) public auditHistory;

    /// @notice Pending audit requests queue
    mapping(bytes32 => AuditRequest) public auditRequests;

    /// @notice Authorized guardian agents that can write results
    mapping(address => bool) public authorizedAgents;

    /// @notice Registry owner
    address public owner;

    /// @notice Total audits completed
    uint256 public totalAudits;

    /// @notice Total unique contracts audited
    uint256 public totalContracts;

    // ─── Events ───────────────────────────────────────────────────────────────

    event AuditRequested(
        bytes32 indexed requestId,
        address indexed contractAddress,
        address indexed requester,
        uint256 timestamp
    );

    event AuditCompleted(
        bytes32 indexed requestId,
        address indexed contractAddress,
        RiskLevel riskLevel,
        uint8 riskScore,
        bytes32 storageHash,
        uint256 timestamp
    );

    event AgentAuthorized(address indexed agent);
    event AgentRevoked(address indexed agent);

    // ─── Errors ───────────────────────────────────────────────────────────────

    error NotOwner();
    error NotAuthorizedAgent();
    error InvalidContractAddress();
    error RequestNotFound();
    error AlreadyCompleted();

    // ─── Modifiers ────────────────────────────────────────────────────────────

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyAgent() {
        if (!authorizedAgents[msg.sender]) revert NotAuthorizedAgent();
        _;
    }

    // ─── Constructor ──────────────────────────────────────────────────────────

    constructor() {
        owner = msg.sender;
        authorizedAgents[msg.sender] = true;
    }

    // ─── User Functions ───────────────────────────────────────────────────────

    /**
     * @notice Request an AI audit for a deployed contract.
     * @param contractAddress The address of the contract to audit.
     * @param sourceCodeHash  Optional keccak256 of submitted Solidity source.
     * @return requestId      Unique ID for tracking this audit request.
     */
    function requestAudit(
        address contractAddress,
        string calldata sourceCodeHash
    ) external returns (bytes32 requestId) {
        if (contractAddress == address(0)) revert InvalidContractAddress();

        requestId = keccak256(
            abi.encodePacked(contractAddress, msg.sender, block.timestamp, block.number)
        );

        auditRequests[requestId] = AuditRequest({
            contractAddress: contractAddress,
            requester: msg.sender,
            requestTimestamp: block.timestamp,
            status: AuditStatus.PENDING,
            sourceCodeHash: sourceCodeHash
        });

        emit AuditRequested(requestId, contractAddress, msg.sender, block.timestamp);
    }

    // ─── Agent Functions ──────────────────────────────────────────────────────

    /**
     * @notice Submit completed audit results. Called by authorized Guardian agents.
     * @param requestId      The audit request identifier.
     * @param riskLevel      Overall risk classification.
     * @param riskScore      Numeric score 0-100.
     * @param storageHash    0G Storage content hash of the full JSON report.
     * @param storageUrl     0G Storage URL to retrieve the full report.
     * @param counts         [critical, high, medium, low] finding counts.
     * @param agentVersion   Version string of the guardian agent.
     */
    function submitAuditResult(
        bytes32 requestId,
        RiskLevel riskLevel,
        uint8 riskScore,
        bytes32 storageHash,
        string calldata storageUrl,
        uint32[4] calldata counts,
        string calldata agentVersion
    ) external onlyAgent {
        AuditRequest storage req = auditRequests[requestId];
        if (req.requester == address(0)) revert RequestNotFound();
        if (req.status == AuditStatus.COMPLETED) revert AlreadyCompleted();

        req.status = AuditStatus.COMPLETED;

        AuditRecord memory record = AuditRecord({
            contractAddress: req.contractAddress,
            requester: req.requester,
            timestamp: block.timestamp,
            riskLevel: riskLevel,
            riskScore: riskScore,
            storageHash: storageHash,
            storageUrl: storageUrl,
            criticalCount: counts[0],
            highCount: counts[1],
            mediumCount: counts[2],
            lowCount: counts[3],
            status: AuditStatus.COMPLETED,
            agentVersion: agentVersion
        });

        // Store latest record
        bool isNew = auditRecords[req.contractAddress].timestamp == 0;
        auditRecords[req.contractAddress] = record;

        // Append to history
        auditHistory[req.contractAddress].push(record);

        totalAudits++;
        if (isNew) totalContracts++;

        emit AuditCompleted(
            requestId,
            req.contractAddress,
            riskLevel,
            riskScore,
            storageHash,
            block.timestamp
        );
    }

    // ─── View Functions ───────────────────────────────────────────────────────

    /**
     * @notice Get the latest audit record for a contract.
     */
    function getAuditRecord(address contractAddress)
        external view returns (AuditRecord memory)
    {
        return auditRecords[contractAddress];
    }

    /**
     * @notice Get full audit history for a contract.
     */
    function getAuditHistory(address contractAddress)
        external view returns (AuditRecord[] memory)
    {
        return auditHistory[contractAddress];
    }

    /**
     * @notice Check if a contract has been audited and is safe.
     * @return audited  Whether any audit exists.
     * @return safe     Whether latest audit has no critical/high findings.
     * @return score    The numeric risk score (0=safe, 100=critical).
     */
    function isContractSafe(address contractAddress)
        external view returns (bool audited, bool safe, uint8 score)
    {
        AuditRecord memory record = auditRecords[contractAddress];
        audited = record.timestamp > 0;
        safe = audited && record.criticalCount == 0 && record.highCount == 0;
        score = record.riskScore;
    }

    /**
     * @notice Get audit request details.
     */
    function getAuditRequest(bytes32 requestId)
        external view returns (AuditRequest memory)
    {
        return auditRequests[requestId];
    }

    // ─── Admin Functions ──────────────────────────────────────────────────────

    function authorizeAgent(address agent) external onlyOwner {
        authorizedAgents[agent] = true;
        emit AgentAuthorized(agent);
    }

    function revokeAgent(address agent) external onlyOwner {
        authorizedAgents[agent] = false;
        emit AgentRevoked(agent);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        owner = newOwner;
    }
}
