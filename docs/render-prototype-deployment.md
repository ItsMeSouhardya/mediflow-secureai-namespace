# Render prototype deployment runbook

This repository includes a Render Blueprint (`render.yaml`) for the React
static site, Flask web service, free PostgreSQL database, and free Key Value
instance. Documents use a private Cloudflare R2 bucket. The blockchain outbox
is processed hourly by GitHub Actions.

Use synthetic demonstration data only. The free services are not appropriate
for real medical data or production workloads.

## 1. Commit the generated contract artifact

The Flask API reads the Hardhat artifact at runtime. Generate it before the
deployment commit:

```powershell
npm ci --prefix blockchain
npm run compile --prefix blockchain
git add -f blockchain/artifacts/contracts/MediFlowIntegrity.sol/MediFlowIntegrity.json
```

Repeat the compile and force-add commands whenever the Solidity contract
changes.

## 2. Generate and save secrets

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate-deployment-secrets.ps1
```

Store the five resulting values in a password manager. In particular, losing
`DOCUMENT_ENCRYPTION_KEY` makes uploaded documents unrecoverable.

## 3. Create Cloudflare R2 storage

1. Create a private R2 bucket named `mediflow-documents`.
2. Create an object read/write token scoped only to that bucket.
3. Record the bucket name, account ID, access key, and secret key.
4. Build the endpoint as
   `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.

Do not enable public bucket access.

## 4. Create the Render Blueprint

1. Push this repository to GitHub.
2. In Render, select **New > Blueprint** and connect the repository.
3. Render reads `render.yaml`; accept the three free resources and static site.
4. When prompted, enter:

   | Render variable | Value |
   |---|---|
   | `SECRET_KEY` | Generated secret |
   | `JWT_SECRET_KEY` | Generated secret |
   | `METRICS_SECRET_KEY` | Generated secret |
   | `BLOCKCHAIN_REFERENCE_SECRET` | Generated secret |
   | `DOCUMENT_ENCRYPTION_KEY` | Generated Fernet key |
   | `DOCUMENT_S3_BUCKET` | `mediflow-documents` |
   | `DOCUMENT_S3_ENDPOINT_URL` | R2 endpoint from step 3 |
   | `DOCUMENT_S3_ACCESS_KEY` | R2 access key |
   | `DOCUMENT_S3_SECRET_KEY` | R2 secret key |

The Blueprint names are intentionally fixed because the frontend rewrite and
CORS allowlist refer to those names. If Render reports a name collision, change
both service `name` values and update the rewrite destination,
`CORS_ORIGINS`, and the workflow's `CORS_ORIGINS` before creating the
Blueprint.

Verify these endpoints after the first deploy:

```text
https://mediflow-secureai-souhardya-api.onrender.com/api/v1/health
https://mediflow-secureai-souhardya.onrender.com/api/v1/health
```

## 5. Deploy the contract to Sepolia

Create a dedicated demo wallet with no real funds, obtain Sepolia test ETH,
and create a Sepolia RPC URL. Then run:

```powershell
$env:BLOCKCHAIN_RPC_URL="https://your-sepolia-rpc-url"
$env:BLOCKCHAIN_CHAIN_ID="11155111"
$env:BLOCKCHAIN_DEPLOYER_PRIVATE_KEY="0xYOUR_DEMO_PRIVATE_KEY"
Push-Location blockchain
npx hardhat run scripts/deploy.cjs --network configured
Pop-Location
```

Record the printed contract address. Never commit the wallet private key.

## 6. Enable blockchain reads in the Render API

Add these environment variables to the Render API service:

```text
BLOCKCHAIN_ENABLED=true
BLOCKCHAIN_RPC_URL=<Sepolia RPC URL>
BLOCKCHAIN_CHAIN_ID=11155111
BLOCKCHAIN_CONTRACT_ADDRESS=<deployed address>
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY=<dedicated demo-wallet private key>
BLOCKCHAIN_REFERENCE_SECRET=<same saved value used during Blueprint creation>
```

Redeploy the API and confirm the health endpoint still succeeds.

## 7. Configure the free GitHub Actions worker

In **GitHub > Settings > Secrets and variables > Actions**, add:

```text
DATABASE_URL
SECRET_KEY
JWT_SECRET_KEY
DOCUMENT_ENCRYPTION_KEY
BLOCKCHAIN_RPC_URL
BLOCKCHAIN_CONTRACT_ADDRESS
BLOCKCHAIN_DEPLOYER_PRIVATE_KEY
BLOCKCHAIN_REFERENCE_SECRET
```

Use the Render database's **External Database URL** for `DATABASE_URL`. The
application automatically converts Render's `postgresql://` scheme to the
installed psycopg 3 driver. Keep SSL enabled in the supplied external URL.

The blockchain and reference-secret values must match Render. The worker's
Flask/JWT values can use the same saved values for operational simplicity.

Open **GitHub > Actions > Blockchain Processor**, enable the workflow if
needed, and run it manually once. The checked-in schedule then runs at minute
7 of every hour.

## 8. Optional demo data and final checks

Free Render web services do not provide shell access. To seed synthetic data,
temporarily insert this command between `db upgrade` and `gunicorn` in the API
start command:

```text
python -m flask --app app seed-demo &&
```

Deploy once, then remove it and redeploy so normal starts never seed data.

Before the demonstration, verify login, document upload/download, the private
R2 object, telemedicine join URLs, an outbox transaction, the manual GitHub
worker run, and the resulting transaction on Sepolia Etherscan.
