# Task 16 integrated demonstration

Task 16 uses PostgreSQL, Redis, a local Hardhat chain, the Flask API, and the Vite frontend. The blockchain service installs its dependencies on the first start, so wait for its Docker health status instead of deploying immediately after the container is created.

## Start the integrated backend

From the repository root in PowerShell:

```powershell
.\scripts\start-task16-demo.ps1
```

The launcher starts PostgreSQL, Redis, and Hardhat; waits for JSON-RPC readiness; deploys `MediFlowIntegrity`; reads the generated deployment address; enables the safe local unlocked-account mode; and starts Flask. The unlocked-account mode is rejected by production configuration.

In a second PowerShell terminal, start the frontend:

```powershell
npm run dev
```

Open `http://localhost:5173/demo` for the serial walkthrough. Use the actual patient, doctor, hospital-admin, and security-admin screens linked from that page. Patient-visible access history is available at `/integrity` and is scoped by the API to the authenticated patient's resources.

## Repeatable checks

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_phase8_blockchain.py backend\tests\test_phase15_e2e.py
npm run build
docker compose --profile blockchain ps
```

The local contract deployment is written to `blockchain/deployments/31337.json`. Do not commit private keys or place raw medical data on-chain; only hashes and opaque references are anchored.
