const { ethers } = require("hardhat");
const fs = require("fs");

async function main() {
  const [deployer] = await ethers.getSigners();

  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log("  0G Guardian — AuditRegistry Deployment");
  console.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
  console.log(`Deployer:  ${deployer.address}`);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log(`Balance:   ${ethers.formatEther(balance)} ETH`);

  const network = await ethers.provider.getNetwork();
  console.log(`Network:   ${network.name} (chainId: ${network.chainId})`);
  console.log("─────────────────────────────────────────");

  // Deploy AuditRegistry
  console.log("\nDeploying AuditRegistry...");
  const AuditRegistry = await ethers.getContractFactory("AuditRegistry");
  const registry = await AuditRegistry.deploy();
  await registry.waitForDeployment();

  const address = await registry.getAddress();
  console.log(`✅ AuditRegistry deployed to: ${address}`);

  // Verify deployment
  const owner = await registry.owner();
  console.log(`✅ Contract owner: ${owner}`);
  console.log(`✅ Deployer is authorized agent: ${await registry.authorizedAgents(deployer.address)}`);

  // Save deployment info
  const deploymentInfo = {
    network: network.name,
    chainId: network.chainId.toString(),
    contractAddress: address,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    txHash: registry.deploymentTransaction()?.hash || "unknown",
  };

  const outPath = `deployments/${network.name}_${network.chainId}.json`;
  fs.mkdirSync("deployments", { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(deploymentInfo, null, 2));
  console.log(`\n📄 Deployment info saved to: ${outPath}`);

  console.log("\n─────────────────────────────────────────");
  console.log("Next steps:");
  console.log(`  1. Add to .env:  REGISTRY_ADDRESS=${address}`);
  console.log(`  2. Run agent:    python agent/guardian_agent.py`);
  console.log(`  3. Test:         python scripts/test_full_flow.py`);
  console.log("─────────────────────────────────────────\n");

  return address;
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("Deployment failed:", error);
    process.exit(1);
  });
