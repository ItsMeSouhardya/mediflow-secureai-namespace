# Electronic Health Record domain

Task 4 introduces a longitudinal EHR domain while preserving the identity, tenancy, and clinical-access boundaries established in Task 3.

## Record structure

- `patient_profiles` provides the one-to-one clinical identity attached to a Patient user and a non-public medical-record number.
- `doctor_profiles` connects an authenticated Doctor user to a hospital and the existing provider-directory record.
- `encounters` anchor a visit to a patient, hospital, department, doctor, appointment, and/or queue token.
- `diagnoses`, `prescriptions`, `allergies`, and `vaccinations` retain structured clinical information.
- `clinical_changes` is append-only application history containing actor, action, reason, request context, before snapshot, after snapshot, and timestamp.
- Existing `appointments` and `tokens` carry `patient_profile_id` so operational workflows resolve to the same longitudinal patient record.

## Authorization model

A patient can retrieve only the EHR profile resolved from the authenticated user.

A doctor can discover or retrieve a patient only when at least one explicit care relationship exists:

1. an appointment assigned to the doctor's provider-directory record;
2. a queue token assigned to that provider; or
3. an encounter assigned to the authenticated doctor profile.

Hospital membership alone is insufficient. Encounter creation also verifies that its appointment or token belongs to the selected patient and doctor and remains inside the doctor's hospital tenant. Security and hospital administrators do not receive clinical endpoints.

This assignment-based authorization path is intentionally narrower than the consent and delegation system planned for Task 7. Task 7 can extend the same authorization check with patient grants, emergency break-glass access, expiry, and revocation.

## Versioned endpoints

Patient:

- `GET /api/v1/patients/me/ehr`

Doctor:

- `GET /api/v1/doctors/me/patients`
- `GET /api/v1/doctors/me/patients/{patient_id}`
- `POST /api/v1/doctors/me/encounters`
- `PATCH /api/v1/doctors/me/encounters/{encounter_id}`
- `POST /api/v1/doctors/me/encounters/{encounter_id}/diagnoses`
- `PATCH /api/v1/doctors/me/diagnoses/{diagnosis_id}`
- `POST /api/v1/doctors/me/encounters/{encounter_id}/prescriptions`
- `PATCH /api/v1/doctors/me/prescriptions/{prescription_id}`
- `POST /api/v1/doctors/me/patients/{patient_id}/allergies`
- `POST /api/v1/doctors/me/patients/{patient_id}/vaccinations`

Every clinical mutation requires a human-readable `reason`. Mutation services append a `clinical_changes` record and routes add a durable security audit event in the same database transaction.
