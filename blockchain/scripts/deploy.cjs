const fs = require('fs')
const path = require('path')
const hre = require('hardhat')

async function main() {
  const contract = await hre.ethers.deployContract('MediFlowIntegrity')
  await contract.waitForDeployment()
  const address = await contract.getAddress()
  const network = await hre.ethers.provider.getNetwork()
  const deployment = {
    contract: 'MediFlowIntegrity',
    address,
    chainId: Number(network.chainId),
    deployedAt: new Date().toISOString(),
  }
  const outputDir = path.join(__dirname, '..', 'deployments')
  fs.mkdirSync(outputDir, { recursive: true })
  fs.writeFileSync(path.join(outputDir, `${deployment.chainId}.json`), JSON.stringify(deployment, null, 2))
  console.log(JSON.stringify(deployment))
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
