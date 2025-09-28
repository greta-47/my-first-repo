# API Design & Patterns

## API Conventions

### Base Standards
- **Base path**: `/v1` for all endpoints
- **JSON format**: `snake_case` for all field names
- **Content type**: `application/json` only
- **HTTP methods**: Standard REST semantics (GET, POST, PUT, PATCH, DELETE)

### Authentication & Headers
```http
Authorization: Bearer <JWT>
X-Request-Id: 01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z
Content-Type: application/json
Idempotency-Key: unique-operation-key-123
```

### Versioning Strategy
- **Path-based versioning**: `/v1/`, `/v2/` for breaking changes
- **Backward compatibility**: Maintain v1 for 12+ months after v2 release
- **Deprecation headers**: `Sunset` header with end-of-life date

## Response Envelope Standards

### Success Response
```json
{
  "status": "ok",
  "data": {
    "id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "display_code": "MEMBER_001",
    "state": "active",
    "created_at": "2025-09-27T10:30:00Z"
  },
  "meta": {
    "request_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "version": "v1",
    "timestamp": "2025-09-27T10:30:00Z"
  }
}
```

### Error Response (Problem Details Style)
```json
{
  "status": "error",
  "error": {
    "type": "https://recoveryos.org/errors/validation",
    "title": "Validation Failed",
    "detail": "The sleep_hours field must be between 0 and 24",
    "code": "E_VALIDATION_FAILED",
    "fields": {
      "sleep_hours": ["Must be between 0 and 24"],
      "adherence": ["Must be between 0 and 100"]
    },
    "help_url": "https://docs.recoveryos.org/api/validation-errors"
  },
  "meta": {
    "request_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "timestamp": "2025-09-27T10:30:00Z"
  }
}
```

### HTTP Status Codes
- **200**: Success (GET, PATCH)
- **201**: Created (POST)
- **204**: No Content (DELETE)
- **400**: Bad Request (validation errors)
- **401**: Unauthorized (invalid/missing JWT)
- **403**: Forbidden (insufficient permissions)
- **404**: Not Found
- **409**: Conflict (duplicate resource)
- **422**: Unprocessable Entity (business logic errors)
- **429**: Too Many Requests (rate limited)
- **500**: Internal Server Error

## Pagination Standards

### Cursor-Based Pagination
```json
// Request
GET /v1/check-ins?page[size]=20&cursor=eyJpZCI6IjAxSjdLOE05TjAifQ

// Response
{
  "status": "ok",
  "data": [
    { "id": "...", "adherence": 85, "created_at": "..." }
  ],
  "meta": {
    "pagination": {
      "next_cursor": "eyJpZCI6IjAxSjdLOE05TjBQMVEyUjNTNFQ1VTZWNyJ9",
      "has_more": true,
      "size": 20
    }
  }
}
```

## Rate Limiting

### Check-in Endpoint Protection
```http
// Headers on rate limit hit
HTTP/1.1 429 Too Many Requests
Retry-After: 10
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 0  
X-RateLimit-Reset: 1695812400

{
  "status": "error", 
  "error": {
    "type": "https://recoveryos.org/errors/rate-limit",
    "title": "Rate Limit Exceeded",
    "detail": "Maximum 5 check-ins per 10 seconds allowed",
    "code": "E_RATE_LIMITED"
  }
}
```

## Core API Endpoints

### Check-ins
```http
POST /v1/check-ins
Content-Type: application/json
Idempotency-Key: checkin-20250927-103000-user123

{
  "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
  "adherence": 85,
  "mood_trend": 2,
  "cravings": 15,
  "sleep_hours": 7.5,
  "isolation": 20,
  "notes": "Feeling better today, went for a walk"
}

// Response
{
  "status": "ok",
  "data": {
    "id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z", 
    "adherence": 85,
    "mood_trend": 2,
    "cravings": 15,
    "sleep_hours": 7.5,
    "isolation": 20,
    "notes_redacted": "Feeling [EMOTION] today, went for [ACTIVITY]",
    "created_at": "2025-09-27T10:30:00Z"
  }
}
```

### Risk Scoring
```http
GET /v1/members/01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z/risk-score

{
  "status": "ok",
  "data": {
    "id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
    "score": 45,
    "band": "elevated", 
    "model_version": "v0.1.0",
    "explanations": {
      "primary_factors": ["sleep_disruption", "mood_decline"],
      "protective_factors": ["high_adherence", "low_isolation"],
      "confidence": 0.87
    },
    "grace_period": false,
    "created_at": "2025-09-27T10:30:00Z"
  }
}

// During grace period (<3 check-ins or <N days)
{
  "status": "ok", 
  "data": {
    "band": "no_data",
    "score": null,
    "grace_period": true,
    "days_remaining": 2,
    "checkins_needed": 1
  }
}
```

### Consent Management
```http
POST /v1/consents
{
  "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
  "grantee_type": "clinician", 
  "scope": ["view_risk_scores", "receive_alerts"],
  "terms_version": "2025.1"
}

PATCH /v1/consents/01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z
{
  "status": "revoked"
}
```

### Family Sharing
```http
POST /v1/shares/family
{
  "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
  "contact_method": "sms",
  "contact_value": "+1-555-0123", # Hashed server-side
  "notification_types": ["weekly_summary", "high_risk_alerts"]
}

// Triggers SMS confirmation
// "RecoveryOS: [MEMBER_DISPLAY_CODE] has requested to share updates with you. Reply YES to confirm or NO to decline."
```

### Clinical Alerts
```http
GET /v1/alerts?status=open&severity=high,critical
{
  "status": "ok",
  "data": [
    {
      "id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
      "member_display_code": "MEMBER_001",
      "severity": "high",
      "kind": "risk",
      "message": "Risk score elevated to HIGH band",
      "metadata": {
        "previous_band": "moderate",
        "current_score": 78,
        "trigger_factors": ["sleep_disruption", "mood_decline"]
      },
      "created_at": "2025-09-27T10:30:00Z"
    }
  ]
}

POST /v1/alerts/01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z:acknowledge
{
  "notes": "Reaching out to member for check-in call"
}
```

### Messaging (SMS)
```http
POST /v1/messages:send
{
  "member_id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z",
  "template_key": "weekly_checkin_reminder",
  "variables": {
    "display_code": "MEMBER_001",
    "streak_days": 7
  }
}

// Server-side template rendering - never echo raw PHI
{
  "status": "ok",
  "data": {
    "id": "01J7K8M9N0P1Q2R3S4T5U6V7W8X9Y0Z", 
    "status": "queued",
    "template_key": "weekly_checkin_reminder",
    "estimated_delivery": "2025-09-27T10:35:00Z"
    // Never return actual message content or phone numbers
  }
}
```

## Security Headers

### Response Headers (Applied by Middleware)
```http
Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https:; font-src 'self' data:
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY  
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### CORS Configuration
```python
# Environment-specific CORS origins
ALLOWED_ORIGINS = {
    "dev": [
        "http://localhost:3000",
        "http://localhost:5173", 
        "http://127.0.0.1:3000"
    ],
    "production": [
        "https://recoveryos.org",
        "https://app.recoveryos.org"
    ]
}
```

## Idempotency

### POST Operations
```http
POST /v1/check-ins
Idempotency-Key: checkin-user123-20250927-103000

// First request: Creates new check-in, returns 201
// Duplicate request: Returns existing check-in, returns 200
// Different payload with same key: Returns 409 Conflict
```

## Error Handling Examples

### Validation Error (400)
```json
{
  "status": "error",
  "error": {
    "type": "https://recoveryos.org/errors/validation", 
    "title": "Validation Failed",
    "code": "E_VALIDATION_FAILED",
    "fields": {
      "sleep_hours": ["Must be between 0 and 24"],
      "member_id": ["Required field is missing"]
    }
  }
}
```

### Business Logic Error (422) 
```json
{
  "status": "error",
  "error": {
    "type": "https://recoveryos.org/errors/business-rule",
    "title": "Insufficient Data", 
    "detail": "Risk scoring requires at least 3 check-ins",
    "code": "E_INSUFFICIENT_DATA"
  }
}
```

### Authorization Error (403)
```json
{
  "status": "error", 
  "error": {
    "type": "https://recoveryos.org/errors/authorization",
    "title": "Access Denied",
    "detail": "No consent granted for viewing this member's risk scores",
    "code": "E_CONSENT_REQUIRED"
  }
}
```