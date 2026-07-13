# API v1 Foundation

## Compatibility strategy

- Existing frontend calls under `/api/...` remain available temporarily and keep their legacy payload shapes.
- New integrations use `/api/v1/...`.
- Both route families execute the same validated service functions.
- `/api/v1` responses use a stable envelope and include a request ID.

## Success envelope

```json
{
  "status": "success",
  "data": {},
  "meta": {
    "request_id": "trace-or-generated-uuid",
    "timestamp": "2026-07-12T00:00:00+00:00"
  }
}
```

Collection endpoints include `meta.pagination` with `page`, `per_page`, `total`, and `total_pages`.

## Error envelope

```json
{
  "status": "error",
  "error": {
    "code": "validation_error",
    "message": "Request body is invalid",
    "details": [
      {
        "field": "age",
        "message": "Input should be less than or equal to 130",
        "type": "less_than_equal"
      }
    ]
  },
  "meta": {
    "request_id": "trace-or-generated-uuid",
    "timestamp": "2026-07-12T00:00:00+00:00"
  }
}
```

Validation details never echo submitted values.

## Request tracing

- Clients may send `X-Request-ID` containing 8–64 letters, numbers, dots, underscores, or hyphens.
- Invalid or absent values are replaced by a generated UUID.
- Every response contains `X-Request-ID`.
- Structured logs record method, path, status, duration, remote address, and request ID without logging query strings or request bodies.

## Pagination and filters

Supported collection parameters:

- `page`: integer, minimum 1
- `per_page`: integer, 1–100
- `sort_order`: `asc` or `desc`
- `search`: at most 100 characters
- `date_from`: ISO date
- `date_to`: ISO date and not before `date_from`

## Idempotency

`POST /api/v1/tokens/book` requires `Idempotency-Key`.

- Keys are 8–128 safe ASCII characters.
- Replaying the same key and request returns the stored result and `Idempotent-Replayed: true`.
- Reusing a key with different input returns HTTP 409.
- Records expire after 24 hours.
- The helper is reusable by future consent and sharing services.

## Rate-limit policies

| Capability | Policy |
|---|---:|
| Authentication | 10/minute |
| Document upload | 10/minute |
| AI prediction/analysis | 30/minute |
| Token booking | 10/minute |
| Token lookup | 60/minute |
| Record sharing/consent | 20/minute |
| Other sensitive writes | 30/minute |

The current prediction, booking, lookup, and prototype record-write endpoints enforce their policies. Authentication, upload, and sharing modules must import the predefined policies when those routes are introduced.

## Browser and transport controls

- Explicit CORS allowlist; wildcard origins are rejected at startup.
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- Restrictive Permissions Policy and API Content Security Policy
- `Cache-Control: no-store` for API responses
- HSTS and secure cookies in production

## Audit boundary

`write_audit_event` records actor, action, resource, outcome, request ID, source address, user agent, and non-sensitive details. Passwords, tokens, symptoms, document contents, and secrets are rejected from the details payload by key.
