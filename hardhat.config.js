require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config();

const PRIVATE_KEY = process.env.PRIVATE_KEY || "0x" + "0".repeat(64);

/** @type import('hardhat/config').HardhatUserConfig */
module.exports = {
  solidity: {
    version: "0.8.20",
    settings: {
      optimizer: {
        enabled: true,
        runs: 200,
      },
    },
  },
  networks: {
    // 0G Galileo Testnet
    og_testnet: {
      url: process.env.OG_CHAIN_RPC || "https://evmrpc-testnet.0g.ai",
      chainId: 16601,
      accounts: [PRIVATE_KEY],
      gasPrice: "auto",
    },
    // 0G Mainnet (Wave 3+)
    og_mainnet: {
      url: process.env.OG_MAINNET_RPC || "https://evmrpc.0g.ai",
      chainId: 16600,
      accounts: [PRIVATE_KEY],
      gasPrice: "auto",
    },
    // Local development
    hardhat: {
      chainId: 31337,
    },
  },
  etherscan: {
    apiKey: {
      og_testnet: process.env.OG_EXPLORER_API_KEY || "no-api-key-needed",
    },
    customChains: [
      {
        network: "og_testnet",
        chainId: 16601,
        urls: {
          apiURL: "https://chainscan-galileo.0g.ai/api",
          browserURL: "https://chainscan-galileo.0g.ai",
        },
      },
    ],
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
