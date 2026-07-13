<img width="4320" height="1440" alt="HackHazards 2026 project banner" src="https://github.com/user-attachments/assets/c698b2cd-da84-4cb0-9276-125c6a7244aa" />

# MediFlow SecureAI

> A secure, AI-assisted hospital operations platform for smarter queues, connected care, protected health records, and verifiable data integrity.

---

## 📌 Problem & Domain

Hospitals often operate with fragmented patient information, uncertain waiting times, overcrowded departments, and limited visibility into urgent cases. Patients cannot plan visits confidently, while staff lack a single secure workspace for queue management, clinical coordination, monitoring, and record sharing.

MediFlow SecureAI is a HealthTech prototype that brings these workflows together while treating privacy, consent, and data integrity as first-class concerns.

**Themes selected:**

- [x] HealthTech & Bio Platforms
- [x] Human Experience & Productivity
- [x] Trust, Identity & Security
- [x] Infrastructure, Mobility & Smart Systems

---

## 🎯 Objective

MediFlow SecureAI serves patients, clinicians, hospital administrators, and operational teams.

- **Patients** can book and track tokens, receive wait-time estimates, view health information, share records with explicit consent, and join telemedicine sessions.
- **Clinical staff** can review patient records, manage encounters, monitor patient observations, and respond to alerts.
- **Hospital teams** can see live department load, manage queues, reduce avoidable crowding, and identify operational bottlenecks.
- **Security teams** receive audit trails, security events, role-based access controls, encrypted document handling, and optional blockchain integrity proofs.

---

## 🧠 Team & Approach

### Team Name

`Add your team name here`

### Team Members

- Add member name — role / GitHub / LinkedIn
- Add member name — role / GitHub / LinkedIn
- Add member name — role / GitHub / LinkedIn
- Add member name — role / GitHub / LinkedIn

### Our Approach

We approached hospital flow as both an operational and a trust problem. The prototype combines a patient-facing queue experience with clinician and administrator workspaces, while keeping sensitive features behind authentication, consent checks, encryption, audit logging, and integrity verification. The architecture is modular so the system can be demonstrated locally or deployed as a cloud prototype.

---

## 🛠️ Tech Stack

| Area | Technologies |
| --- | --- |
| Frontend | React, Vite, React Router, Tailwind CSS |
| Backend | Python, Flask, SQLAlchemy, Alembic, Pydantic |
| Database | PostgreSQL |
| Cache / rate limiting | Redis, Flask-Limiter |
| Security | Argon2 password hashing, JWT, RBAC, audit logging, Fernet document encryption |
| Document storage | Local development storage or S3-compatible object storage such as Backblaze B2 |
| Blockchain | Solidity, Hardhat, Web3.py, Ethereum Sepolia, Alchemy |
| Deployment | Render, GitHub Actions |

---

## ✨ Key Features

- **Smart queue and token booking** with department load, live token progress, and estimated wait times.
- **Emergency symptom triage** to identify urgency and suggest appropriate care pathways.
- **Hospital dashboards** for department load, queue capacity, crowd indicators, and staff operations.
- **Secure patient accounts** with registration, login, role-based access, session handling, and account controls.
- **Electronic health records** for encounters, diagnoses, prescriptions, allergies, vaccinations, and patient history.
- **Encrypted document pipeline** with protected upload, download, sharing, verification, and object-storage support.
- **Consent-based sharing** between patients and clinicians, including auditable access and emergency break-glass workflows.
- **Patient monitoring and alerts** with deterministic simulations, vital trends, and clinician-facing notifications.
- **Telemedicine session support** using Jitsi meeting links.
- **Security operations** including audit events, explainable rules, anomaly datasets, temporary controls, and recovery guidance.
- **Blockchain integrity layer** that can anchor asynchronous document and audit evidence to Ethereum Sepolia.

---

## 📁 Project Structure

```text
.
├── src/                  # React frontend pages, components, API client, and auth state
├── backend/              # Flask API, models, routes, migrations, tests, and scripts
├── blockchain/           # Solidity contract, Hardhat configuration, tests, and deploy script
├── docs/                 # Architecture, API, security, monitoring, and deployment guides
├── public/               # Static assets and demonstration documents
├── .github/workflows/    # CI and scheduled blockchain processor workflow
├── compose.yaml          # Local PostgreSQL, Redis, and optional local blockchain services
├── render.yaml           # Render Blueprint configuration
└── .env.example          # Environment-variable reference
```

---

## 🧪 How to Run the Project Locally

### Prerequisites

- Node.js 20 or newer
- Python 3.11 or newer
- Docker Desktop (recommended for local PostgreSQL and Redis)
- Git

### 1. Clone and configure

```powershell
git clone https://github.com/ItsMeSouhardya/mediflow-secureai-namespace.git
cd mediflow-secureai-namespace
Copy-Item .env.example .env
```

Update the required development values in `.env`, especially `SECRET_KEY`, `JWT_SECRET_KEY`, and `DOCUMENT_ENCRYPTION_KEY`.

### 2. Start PostgreSQL and Redis

```powershell
docker compose up -d postgres redis
```

### 3. Start the Flask API

Open a terminal in the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m flask --app app db upgrade
python -m flask --app app seed-demo
python -m flask --app app run --debug --port 5000
```

### 4. Start the React frontend

Open a second terminal in the repository root:

```powershell
npm ci
npm run dev
```

Open the local URL displayed by Vite, normally `http://localhost:5173`. The Vite development server proxies `/api` requests to Flask on port `5000`.

### Optional: local blockchain

The smart contract lives in `blockchain/`. Install its dependencies and run its tests with:

```powershell
cd blockchain
npm ci
npm run compile
npm test
```

See [blockchain integrity](docs/blockchain-integrity.md) for deployment and integration details.

---

## ☁️ Prototype Deployment Architecture

The project is prepared for a low-cost Render-based prototype deployment:

```text
React frontend  → Render Static Site
Flask API       → Render Web Service
PostgreSQL      → Render Postgres
Redis           → Render Key Value
Documents       → S3-compatible object storage
Blockchain work → GitHub Actions scheduled workflow + Ethereum Sepolia
```

Use [the Render prototype deployment guide](docs/render-prototype-deployment.md) for the full setup, environment variables, storage configuration, and verification checklist.

---

## 🎥 Demo & Deliverables

- **Demo Video Link (Mandatory):** [Paste link]
- **Deployment Link (Recommended):** [Paste link]
- **Pitch Deck / PPT (Optional):** [Paste link]

---

## 🧬 Future Scope

- Integrate validated clinical decision-support models with clear human-review safeguards.
- Add hospital-system interoperability through standards such as FHIR.
- Support production-grade identity management, MFA enforcement, and centralized key management.
- Add observability, backups, disaster-recovery drills, and scaling policies for real-world deployment.
- Expand accessibility, localization, and low-bandwidth patient experiences.
- Move blockchain operations to a dedicated, monitored worker when production scale requires it.

---

## 📎 Documentation & Credits

- [API v1 foundation](docs/api-v1-foundation.md)
- [Electronic health record domain](docs/ehr-domain.md)
- [Monitoring](docs/monitoring.md)
- [Security operations](docs/security-operations.md)
- [Blockchain integrity](docs/blockchain-integrity.md)
- [Deployment guide](docs/deployment.md)
- [Backup and recovery](docs/backup-restore.md)

Core open-source technologies include React, Vite, Flask, SQLAlchemy, PostgreSQL, Redis, Hardhat, Web3.py, and Jitsi.

---

## 🏁 Final Words

MediFlow SecureAI is a prototype for demonstrating how hospital operations, patient experience, security, and verifiable integrity can work together in one platform. It is not a substitute for clinical judgment and is not intended for production medical use without formal security, privacy, regulatory, and clinical validation.
