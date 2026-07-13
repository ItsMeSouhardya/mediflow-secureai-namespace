# Blockchain integrity and immutable proofs

MediFlow treats PostgreSQL and encrypted object storage as the operational system of record. The blockchain layer is an asynchronous integrity proof service; healthcare reads and writes do not wait for it.

## Privacy boundary

The Solidity contract accepts only `bytes32` values. Contract state, calls, and events never receive:

- patient names, emails, phone numbers, UUIDs, or medical-record numbers;
- filenames, document titles, storage references, or extracted text;
- diagnoses, biomarkers, prescriptions, consent purposes, or revocation reasons.

Backend references are HMAC-SHA256 values derived with `BLOCKCHAIN_REFERENCE_SECRET`. Consent scope sets, validity periods, revocations, record content, audit resources, and Merkle leaves are canonicalized and hashed before entering the outbox.

## Local contract workflow

```powershell
cd blockchain
npm install
npm run compile
npm test
npm run node
```

In another terminal:

```powershell
cd blockchain
npm run deploy:local
```

Copy the deployment address into `BLOCKCHAIN_CONTRACT_ADDRESS`, configure the first Hardhat account's private key only in the local `.env`, and set `BLOCKCHAIN_ENABLED=true`.

Never commit deployer keys. Production deployments should use a dedicated signer or external key-management service, restricted RPC access, a separate reference secret, contract-owner rotation/governance, and monitored gas funding.

## Asynchronous outbox

Primary operations create a `blockchain_transactions` row in the same PostgreSQL transaction:

- finalized document versions → `record_register`;
- consent grants and break-glass grants → `consent_grant`;
- consent revocations → `consent_revoke`;
- completed audit periods → `audit_anchor`.

States are `pending`, `submitted`, `confirmed`, `retry`, and `failed`. Submission receipts, chain ID, contract address, transaction hash, block number, attempts, errors, and retry timestamps are retained. Exponential backoff is bounded by `BLOCKCHAIN_RETRY_MAX_ATTEMPTS`.

Run a single development cycle:

```powershell
flask blockchain-worker --once
```

Run continuously under a process supervisor:

```powershell
flask blockchain-worker --interval 30 --limit 50
```

The worker also creates the preceding fixed UTC audit period's Merkle root idempotently. If the RPC, signer, or contract is unavailable, clinical and document operations remain committed and proof rows remain retryable.

## Verification semantics

Document verification has three outcomes:

- `verified`: decrypted source bytes match PostgreSQL and the confirmed contract hash;
- `pending`: local bytes match, but the proof is pending or the chain is unavailable;
- `modified`: local bytes differ from the immutable version hash or the confirmed chain hash.

Patients use `/integrity`; authorized doctors can use the scoped integrity endpoint only with active `reports` consent. Consent grant and revocation transaction states are visible to the owning patient and requesting doctor.
