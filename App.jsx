import { useState } from "react";
import { ethers } from "ethers";

// ── ABI (read-only functions) ─────────────────────────────────────────────────
const REGISTRY_ABI = [
  "function getAuditRecord(address) view returns (tuple(address contractAddress, address requester, uint256 timestamp, uint8 riskLevel, uint8 riskScore, bytes32 storageHash, string storageUrl, uint32 criticalCount, uint32 highCount, uint32 mediumCount, uint32 lowCount, uint8 status, string agentVersion))",
  "function isContractSafe(address) view returns (bool audited, bool safe, uint8 score)",
  "function totalAudits() view returns (uint256)",
  "function totalContracts() view returns (uint256)",
  "function requestAudit(address, string) returns (bytes32)",
];

const REGISTRY_ADDRESS = import.meta.env.VITE_REGISTRY_ADDRESS || "";
const OG_RPC = import.meta.env.VITE_OG_RPC || "https://evmrpc-testnet.0g.ai";

const RISK_LABELS = ["UNKNOWN", "CRITICAL", "HIGH", "MEDIUM", "LOW", "SAFE"];
const RISK_COLORS = {
  CRITICAL: "#FF4444",
  HIGH:     "#FF8800",
  MEDIUM:   "#FFD700",
  LOW:      "#44BBFF",
  SAFE:     "#44FF88",
  UNKNOWN:  "#888888",
};

// ── Helpers ───────────────────────────────────────────────────────────────────
function riskLabel(level) { return RISK_LABELS[level] || "UNKNOWN"; }
function riskColor(label) { return RISK_COLORS[label] || "#888"; }
function shortenHash(h) { return h ? `${h.slice(0, 10)}...${h.slice(-8)}` : "—"; }
function tsToDate(ts) {
  if (!ts || ts === 0n) return "—";
  return new Date(Number(ts) * 1000).toLocaleString();
}

// ── Main App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [input, setInput]       = useState("");
  const [record, setRecord]     = useState(null);
  const [safeStatus, setSafe]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");
  const [stats, setStats]       = useState(null);
  const [requesting, setReq]    = useState(false);
  const [reqTx, setReqTx]       = useState("");

  const provider = new ethers.JsonRpcProvider(OG_RPC);
  const registry = new ethers.Contract(REGISTRY_ADDRESS, REGISTRY_ABI, provider);

  async function loadStats() {
    try {
      const [ta, tc] = await Promise.all([
        registry.totalAudits(),
        registry.totalContracts(),
      ]);
      setStats({ totalAudits: ta.toString(), totalContracts: tc.toString() });
    } catch {}
  }

  async function search() {
    setError(""); setRecord(null); setSafe(null);
    if (!ethers.isAddress(input)) {
      setError("Invalid Ethereum address"); return;
    }
    setLoading(true);
    try {
      const [rec, safe] = await Promise.all([
        registry.getAuditRecord(input),
        registry.isContractSafe(input),
      ]);
      setRecord(rec);
      setSafe({ audited: safe[0], safe: safe[1], score: Number(safe[2]) });
      await loadStats();
    } catch (e) {
      setError(`RPC error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }

  async function requestAudit() {
    setError(""); setReqTx("");
    if (!ethers.isAddress(input)) { setError("Invalid address"); return; }
    if (!window.ethereum) { setError("MetaMask not found"); return; }
    setReq(true);
    try {
      const signer = await new ethers.BrowserProvider(window.ethereum).getSigner();
      const rw = registry.connect(signer);
      const tx = await rw.requestAudit(input, "");
      setReqTx(tx.hash);
      await tx.wait();
      setReqTx(`✅ Confirmed: ${tx.hash}`);
    } catch (e) {
      setError(`Request failed: ${e.message}`);
    } finally {
      setReq(false);
    }
  }

  const rl = record ? riskLabel(Number(record.riskLevel)) : null;
  const hasRecord = record && record.timestamp > 0n;

  return (
    <div style={styles.root}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.logo}>🛡️ 0G Guardian</div>
        <div style={styles.subtitle}>Onchain AI Security Audit Agent</div>
        {stats && (
          <div style={styles.statsRow}>
            <span style={styles.stat}>⚡ {stats.totalAudits} audits</span>
            <span style={styles.stat}>📋 {stats.totalContracts} contracts</span>
            <span style={styles.statBadge}>Powered by 0G</span>
          </div>
        )}
      </header>

      {/* Search */}
      <main style={styles.main}>
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Audit a Contract</h2>
          <div style={styles.searchRow}>
            <input
              style={styles.input}
              placeholder="0x... contract address"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && search()}
            />
            <button style={styles.btnPrimary} onClick={search} disabled={loading}>
              {loading ? "Checking..." : "Check"}
            </button>
          </div>
          {error && <div style={styles.error}>{error}</div>}

          {/* Result */}
          {safeStatus && (
            <div style={styles.resultBox}>
              {safeStatus.audited ? (
                <>
                  {/* Risk Badge */}
                  <div style={{ ...styles.badge, background: riskColor(rl) }}>
                    {rl} — Score: {safeStatus.score}/100
                  </div>

                  {/* Summary row */}
                  <div style={styles.metaGrid}>
                    <MetaItem label="Audited" value={safeStatus.audited ? "✅ Yes" : "❌ No"} />
                    <MetaItem label="Safe" value={safeStatus.safe ? "✅ Yes" : "⚠️ No"} />
                    <MetaItem label="Risk Score" value={`${safeStatus.score}/100`} />
                    <MetaItem label="Audited At" value={tsToDate(record?.timestamp)} />
                    <MetaItem label="Agent Version" value={record?.agentVersion || "—"} />
                  </div>

                  {/* Severity breakdown */}
                  {hasRecord && (
                    <div style={styles.severityRow}>
                      <SevBadge label="CRITICAL" count={Number(record.criticalCount)} />
                      <SevBadge label="HIGH"     count={Number(record.highCount)} />
                      <SevBadge label="MEDIUM"   count={Number(record.mediumCount)} />
                      <SevBadge label="LOW"      count={Number(record.lowCount)} />
                    </div>
                  )}

                  {/* Storage */}
                  {record?.storageUrl && (
                    <div style={styles.storageBox}>
                      <span style={styles.storageLabel}>📦 Full Report (0G Storage)</span>
                      <a href={record.storageUrl} target="_blank" rel="noreferrer"
                         style={styles.storageLink}>
                        {shortenHash(record.storageHash)} ↗
                      </a>
                    </div>
                  )}
                </>
              ) : (
                <div style={styles.notAudited}>
                  <div style={styles.notAuditedIcon}>🔍</div>
                  <div>This contract has not been audited yet.</div>
                  <button
                    style={{ ...styles.btnPrimary, marginTop: 16 }}
                    onClick={requestAudit}
                    disabled={requesting}
                  >
                    {requesting ? "Submitting..." : "Request Audit (Requires Wallet)"}
                  </button>
                  {reqTx && <div style={styles.txNote}>{reqTx}</div>}
                </div>
              )}
            </div>
          )}
        </div>

        {/* How it works */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>How It Works</h2>
          <div style={styles.steps}>
            {[
              ["1", "Submit", "Request an audit for any contract address on 0G Chain"],
              ["2", "Analyze", "Guardian Agent runs Slither static analysis + LLM inference via 0G Compute"],
              ["3", "Store", "Full audit report uploaded to 0G Storage (permanent, content-addressed)"],
              ["4", "Verify", "Risk score & storage hash written to AuditRegistry on 0G Chain — immutable forever"],
            ].map(([n, title, desc]) => (
              <div key={n} style={styles.step}>
                <div style={styles.stepNum}>{n}</div>
                <div>
                  <div style={styles.stepTitle}>{title}</div>
                  <div style={styles.stepDesc}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 0G Components */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>0G Infrastructure</h2>
          <div style={styles.components}>
            {[
              ["0G Chain",   "#4A9EFF", "Smart contract registry — immutable audit records"],
              ["0G Compute", "#44FF88", "LLM inference for AI semantic vulnerability analysis"],
              ["0G Storage", "#FFD700", "Decentralized permanent storage for full audit reports"],
              ["0G Pay",     "#FF8800", "Pay-per-audit billing (Wave 2)"],
            ].map(([name, color, desc]) => (
              <div key={name} style={styles.component}>
                <div style={{ ...styles.componentDot, background: color }} />
                <div>
                  <div style={styles.componentName}>{name}</div>
                  <div style={styles.componentDesc}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </main>

      <footer style={styles.footer}>
        Built on <strong>0G</strong> · Wave 1 · 0G Bridge Buildathon 2026
      </footer>
    </div>
  );
}

function MetaItem({ label, value }) {
  return (
    <div style={styles.metaItem}>
      <div style={styles.metaLabel}>{label}</div>
      <div style={styles.metaValue}>{value}</div>
    </div>
  );
}

function SevBadge({ label, count }) {
  const color = RISK_COLORS[label] || "#888";
  return (
    <div style={{ ...styles.sevBadge, borderColor: color, color }}>
      {count} {label}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────
const styles = {
  root: { minHeight: "100vh", background: "#0D0F1A", color: "#E8E6F0",
          fontFamily: "-apple-system, sans-serif" },
  header: { textAlign: "center", padding: "48px 24px 24px",
            borderBottom: "1px solid rgba(255,255,255,0.08)" },
  logo: { fontSize: 32, fontWeight: 700, letterSpacing: -1 },
  subtitle: { color: "#888", marginTop: 4, fontSize: 14 },
  statsRow: { display: "flex", gap: 16, justifyContent: "center",
              marginTop: 16, flexWrap: "wrap" },
  stat: { background: "rgba(255,255,255,0.06)", padding: "4px 12px",
          borderRadius: 20, fontSize: 13 },
  statBadge: { background: "#1A3FFF22", color: "#4A9EFF", padding: "4px 12px",
               borderRadius: 20, fontSize: 13, border: "1px solid #4A9EFF44" },
  main: { maxWidth: 720, margin: "0 auto", padding: "32px 16px",
          display: "flex", flexDirection: "column", gap: 24 },
  card: { background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 16, padding: 24 },
  cardTitle: { fontSize: 18, fontWeight: 600, marginBottom: 16 },
  searchRow: { display: "flex", gap: 8 },
  input: { flex: 1, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)",
           borderRadius: 8, padding: "10px 14px", color: "#E8E6F0",
           fontSize: 14, outline: "none", fontFamily: "monospace" },
  btnPrimary: { background: "#1A3FFF", color: "#fff", border: "none",
                borderRadius: 8, padding: "10px 20px", cursor: "pointer",
                fontWeight: 600, fontSize: 14, whiteSpace: "nowrap" },
  error: { color: "#FF4444", marginTop: 8, fontSize: 13 },
  resultBox: { marginTop: 20, padding: 20, background: "rgba(0,0,0,0.3)",
               borderRadius: 12, border: "1px solid rgba(255,255,255,0.06)" },
  badge: { display: "inline-block", padding: "6px 16px", borderRadius: 20,
           fontWeight: 700, fontSize: 14, color: "#000", marginBottom: 16 },
  metaGrid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
              gap: 12, marginBottom: 16 },
  metaItem: { background: "rgba(255,255,255,0.04)", borderRadius: 8, padding: "10px 12px" },
  metaLabel: { fontSize: 11, color: "#888", marginBottom: 4, textTransform: "uppercase" },
  metaValue: { fontSize: 13, fontWeight: 500 },
  severityRow: { display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 },
  sevBadge: { border: "1px solid", borderRadius: 6, padding: "4px 10px",
              fontSize: 12, fontWeight: 600 },
  storageBox: { display: "flex", alignItems: "center", gap: 12, fontSize: 13,
                background: "rgba(255,215,0,0.06)", borderRadius: 8,
                padding: "10px 14px", border: "1px solid rgba(255,215,0,0.15)" },
  storageLabel: { color: "#888" },
  storageLink: { color: "#FFD700", textDecoration: "none", fontFamily: "monospace" },
  notAudited: { textAlign: "center", padding: "24px 0", color: "#888" },
  notAuditedIcon: { fontSize: 40, marginBottom: 8 },
  txNote: { marginTop: 8, fontSize: 12, color: "#44FF88", fontFamily: "monospace" },
  steps: { display: "flex", flexDirection: "column", gap: 16 },
  step: { display: "flex", gap: 16, alignItems: "flex-start" },
  stepNum: { background: "#1A3FFF", color: "#fff", borderRadius: "50%",
             width: 28, height: 28, display: "flex", alignItems: "center",
             justifyContent: "center", fontWeight: 700, flexShrink: 0, fontSize: 13 },
  stepTitle: { fontWeight: 600, marginBottom: 2 },
  stepDesc: { color: "#888", fontSize: 13 },
  components: { display: "flex", flexDirection: "column", gap: 12 },
  component: { display: "flex", gap: 12, alignItems: "center" },
  componentDot: { width: 10, height: 10, borderRadius: "50%", flexShrink: 0 },
  componentName: { fontWeight: 600, fontSize: 14 },
  componentDesc: { color: "#888", fontSize: 13 },
  footer: { textAlign: "center", padding: "32px 16px",
            color: "#555", fontSize: 13, borderTop: "1px solid rgba(255,255,255,0.06)" },
};
