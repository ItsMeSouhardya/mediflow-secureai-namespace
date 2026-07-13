"""Central rate-limit policies reused by current and future API modules."""

AUTHENTICATION_RATE_LIMIT = "10 per minute"
DOCUMENT_UPLOAD_RATE_LIMIT = "10 per minute"
PREDICTION_RATE_LIMIT = "30 per minute"
TOKEN_BOOKING_RATE_LIMIT = "10 per minute"
TOKEN_LOOKUP_RATE_LIMIT = "60 per minute"
SHARING_RATE_LIMIT = "20 per minute"
SENSITIVE_WRITE_RATE_LIMIT = "30 per minute"
