# Cybersecurity event collection and threat detection

Task 12 adds a security-specific projection beside the immutable application audit log. Security events contain opaque resource references, hashed network/device fingerprints, categorical metadata, and model features. They never copy document text, symptoms, clinical notes, passwords, tokens, consent reasons, or patient names.

## Event coverage

- Authentication: successful and failed login, token refresh, logout/revocation, password-reset request and completion.
- Authorization: permission denials, consent violations, record access, exports, cross-hospital access, and break-glass use.
- Platform: rate-limit rejection, suspicious/quarantined upload, integrity verification failure, blockchain operation failure, staff/admin actions, and security response actions.

The application audit writer feeds the security collector through an allowlisted metadata projection. Failed authentication and rejected HTTP requests are also collected because those flows may terminate before a normal audit event can be committed.

## Explainable detection rules

| Rule | Trigger | Automated control |
| --- | --- | --- |
| `brute_force_15m` | At least five failed logins for an account/network fingerprint in 15 minutes | Account block for 15 minutes when the account is known |
| `request_burst` | API rate limiter rejects a burst | Network-fingerprint block for 5 minutes |
| `repeated_denials_10m` | At least five permission denials in 10 minutes | Alert only |
| `record_volume_5m` | At least 20 successful record-access events in 5 minutes | Alert only |
| `integrity_failure` | Failed integrity verification | Critical alert |
| `blockchain_failure` | Failed blockchain proof operation | High alert |
| `device_ip_change` | Successful login changes both device and network fingerprints within one hour | Advisory alert |

Duplicate open alerts are coalesced for fifteen minutes. Evidence contains only event IDs, counts, time windows, and model identifiers.

## Controls and recovery

Security administrators can temporarily block accounts, sessions, or network fingerprints. Every block has a reason and expiry. Expired controls are released lazily; administrators can release a control early with mandatory notes. Account, IP, and device allowlist entries prevent automated controls on recovery infrastructure or approved service identities.

`SECURITY_IP_ALLOWLIST` defaults to loopback addresses so local recovery remains possible. Production deployments should replace this with explicitly approved administrative egress addresses and maintain an out-of-band recovery runbook.

## Experimental anomaly scoring

`experimental_distance_v1` scores a sanitized feature vector containing time-of-day encoding, failure/denial flags, device and network novelty, five-minute event volume, and record-access classification. Scores are labeled `advisory_only` in events, alerts, exports, APIs, and the dashboard. They are never consumed by the blocking function.

Generate a deterministic labeled evaluation dataset:

```powershell
python backend/scripts/generate_security_dataset.py --output security-dataset.csv --count 5000 --seed 42
```

Synthetic rows contain no user or clinical data. Real-event dataset exports contain feature vectors and optional analyst labels only.

## Security Admin API

Security Admin endpoints under `/api/v1/security` provide dashboard metrics, filtered event and alert lists, detailed alert history, acknowledgment/investigation/resolution, temporary controls, allowlist management, CSV export, sanitized anomaly datasets, and blockchain/encryption/storage health.

Security administrators remain prohibited from clinical endpoints. The dashboard cannot resolve opaque record references into unrestricted clinical content.
