require('@nomicfoundation/hardhat-ethers')
require('@nomicfoundation/hardhat-chai-matchers')

const privateKey = process.env.BLOCKCHAIN_DEPLOYER_PRIVATE_KEY

module.exports = {
  solidity: {
    version: '0.8.28',
    settings: { optimizer: { enabled: true, runs: 200 } },
  },
  networks: {
    hardhat: { chainId: 31337 },
    localhost: { url: process.env.BLOCKCHAIN_RPC_URL || 'http://127.0.0.1:8545', chainId: 31337 },
    configured: {
      url: process.env.BLOCKCHAIN_RPC_URL || 'http://127.0.0.1:8545',
      chainId: Number(process.env.BLOCKCHAIN_CHAIN_ID || 31337),
      accounts: privateKey ? [privateKey] : [],
    },
  },
}
