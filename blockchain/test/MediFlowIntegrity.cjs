const { expect } = require('chai')
const { ethers, artifacts } = require('hardhat')

const digest = (value) => ethers.sha256(ethers.toUtf8Bytes(value))

describe('MediFlowIntegrity', function () {
  async function deployed() {
    const contract = await ethers.deployContract('MediFlowIntegrity')
    await contract.waitForDeployment()
    return contract
  }

  it('registers and verifies an immutable record hash', async function () {
    const contract = await deployed()
    const recordRef = digest('opaque-record-reference')
    const contentHash = digest('original encrypted document plaintext')
    await expect(contract.registerRecord(recordRef, contentHash)).to.emit(contract, 'RecordRegistered')
    expect(await contract.verifyRecord(recordRef, contentHash)).to.equal(true)
    expect(await contract.verifyRecord(recordRef, digest('modified bytes'))).to.equal(false)
    await expect(contract.registerRecord(recordRef, digest('replacement'))).to.be.reverted
  })

  it('anchors consent grant and revocation proofs without plaintext', async function () {
    const contract = await deployed()
    const consentRef = digest('opaque-consent')
    await expect(contract.grantConsent(
      consentRef,
      digest('opaque-patient'),
      digest('opaque-grantee'),
      digest('canonical-scope-set'),
      digest('opaque-period'),
    )).to.emit(contract, 'ConsentGranted')
    expect((await contract.getConsentProof(consentRef)).active).to.equal(true)
    await expect(contract.revokeConsent(consentRef, digest('revocation-proof'))).to.emit(contract, 'ConsentRevoked')
    expect((await contract.getConsentProof(consentRef)).active).to.equal(false)
  })

  it('anchors a periodic Merkle root', async function () {
    const contract = await deployed()
    const periodRef = digest('period:2026-07-12')
    const root = digest('merkle-root')
    await expect(contract.anchorAuditRoot(periodRef, root)).to.emit(contract, 'AuditRootAnchored')
    const proof = await contract.getAuditAnchor(periodRef)
    expect(proof.merkleRoot).to.equal(root)
  })

  it('rejects mutation by non-owner accounts', async function () {
    const contract = await deployed()
    const [, attacker] = await ethers.getSigners()
    await expect(contract.connect(attacker).registerRecord(digest('ref'), digest('hash'))).to.be.reverted
  })

  it('accepts only fixed-size hashes in mutating contract inputs and events', async function () {
    const artifact = await artifacts.readArtifact('MediFlowIntegrity')
    const allowedFunctions = new Set(['registerRecord', 'grantConsent', 'revokeConsent', 'anchorAuditRoot'])
    for (const entry of artifact.abi) {
      if (entry.type === 'function' && allowedFunctions.has(entry.name)) {
        expect(entry.inputs.every((input) => input.type === 'bytes32')).to.equal(true)
      }
      if (entry.type === 'event') {
        expect(entry.inputs.every((input) => input.type === 'bytes32' || input.type === 'uint64')).to.equal(true)
      }
    }
  })
})
