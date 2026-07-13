# Patient monitoring and realtime alerts

Task 10 separates durable clinical state from transient delivery:

- PostgreSQL stores observation definitions, patient observations, configurable rules, alerts, assignees, status timestamps, and resolution notes.
- Redis carries short-lived pub/sub notifications. Redis is never the system of record.
- Server-Sent Events deliver patient updates on a patient-specific channel and doctor alerts on a doctor-specific channel. Doctor channels are derived only from active `monitoring` consent grants, preventing hospital-wide clinical broadcasts.
- If Redis is unavailable in development or tests, a process-local broker preserves the same API. Production deployments should treat Redis availability as an operational dependency.

## Supported observations

| Type | Unit | Accepted physiological range |
| --- | --- | --- |
| Heart rate | bpm | 20–250 |
| Blood pressure | mmHg | systolic 40–260, diastolic 20–180 |
| Blood oxygen | % | 50–100 |
| Temperature | °C | 30–45 |
| Blood glucose | mg/dL | 20–600 |

Blood-pressure input requires systolic and diastolic values, with systolic greater than diastolic. Recorded timestamps cannot be more than five minutes in the future or more than one year old.

## Alert behavior

Global baseline rules are created lazily the first time monitoring is used. Hospital administrators can add hospital-specific threshold or trend rules. A rule can evaluate minimum/maximum values, secondary blood-pressure values, or change over a configurable number of readings.

Doctors see an alert only when they have a live consent grant containing the `monitoring` scope. Acknowledging or escalating an alert assigns it to that doctor. Resolution requires notes of at least ten characters. Creation, acknowledgment, escalation, resolution, and history access are audited.

## Local operation

Start PostgreSQL and Redis with:

```powershell
docker compose up -d postgres redis
```

Configure `REDIS_URL` (default `redis://localhost:6379/0`) and apply the latest Alembic migration before starting the API.
