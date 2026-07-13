# MediFlow AI – Smart Hospital Queue System Software

MediFlow AI is an AI-powered web platform designed to reduce hospital waiting time and improve patient flow management through intelligent queue prediction and prioritization.

## Demo Features

### 1.Symptom-Based Smart Input  
Users can enter symptoms or token details  
System analyzes input to determine urgency and priority level  

### 2.Wait Time Prediction  
Predicts expected waiting time before hospital visit  
Uses:  
Queue length  
Average consultation time  
Doctor availability  

### 3.Emergency Analyzer  
Detects critical cases based on symptoms  
Automatically assigns higher priority  
Helps avoid delays in emergency situations  

### 4.Real-Time Queue Tracker  
Displays live queue status  
Shows:  
Current token progress  
Estimated wait time  
Enables better planning for patients  

### 5.Smart Hospital & Department Suggestion  
Recommends:  
Appropriate department  
Suitable doctor  
Suggests alternative hospitals if overcrowded  

### 6.AI Smart Report  
Generates a summary report including:  
Predicted wait time  
Priority level  
Suggested actions  

### 7.Hospital Dashboard (Admin View)  
Provides hospitals with:  
Queue monitoring tools  

Patient vital monitoring, deterministic simulation, realtime alerts, and doctor triage are documented in [docs/monitoring.md](docs/monitoring.md).

Cybersecurity event collection, explainable threat rules, temporary controls, advisory anomaly scoring, and recovery procedures are documented in [docs/security-operations.md](docs/security-operations.md).
Patient flow insights  
Helps in resource optimization  

### 8.Token Booking System  
Allows users to:  
View queue  
Plan visits accordingly  
Reduces unnecessary crowding  

## Tech Stack

Frontend: React, Tailwind CSS  
Backend: Python Flask + SQLAlchemy  
AI Engine: Python decision-support rules  
Database: PostgreSQL (Alembic-managed; legacy SQLite migration tooling included)  
Deployment: Render  

## Database Foundation

The runtime now targets PostgreSQL. Configuration is read from `DATABASE_URL`, schema changes are managed through Alembic, and the legacy SQLite file is used only by the one-time migration command.

See `docs/postgresql-migration.md` for provisioning, schema migration, legacy-data import, and verification commands.

## API Foundation

New integrations should use `/api/v1`. Existing `/api` routes remain temporarily available for frontend compatibility. Versioned responses include validated envelopes, request IDs, pagination metadata, rate limits, security headers, idempotency support, and durable audit events.

See `docs/api-v1-foundation.md` for the contract and security conventions.

## Goal

Right Patient → Right Place → Right Time  

## Impact

Reduce waiting time by 20–40%  
Faster emergency response  
Improved hospital workflow  
Better patient experience  

## Future Scope

Integration with real hospital systems  
Advanced ML-based prediction models  
Mobile application  
Government healthcare integration  

## Demo

Deployed Link: [Click Here](https://mediflow-ai-wyt0.onrender.com/)  
Demo Link: [Click Here](https://drive.google.com/file/d/1HiO7Cr18ykhF7igzQjkcgPk7rtssUK-z/edit)

**Devoloper Team :**  
**BitCore Novas**  
***Narula Institute of Technology*** 
