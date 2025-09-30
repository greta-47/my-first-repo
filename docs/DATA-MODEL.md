# Data Model & Safety Patterns

## Core Entities (Minimum Viable)

### Account / Tenant
```sql
CREATE TABLE accounts (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    name TEXT NOT NULL,
    billing_tier TEXT NOT NULL DEFAULT 'basic',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL
);
```

### Clinician
```sql
CREATE TABLE clinicians (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    role TEXT NOT NULL CHECK (role IN ('admin', 'clinician', 'supervisor')),
    email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'suspended')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL
);
```

### Member (Client)
```sql
CREATE TABLE members (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    display_code TEXT NOT NULL, -- Anonymous handle, no names by default
    state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'paused', 'discharged')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ NULL
);
```

### Optional PHI Mirror (Separate Schema/DB)
```sql
-- Lives in phi_schema or separate database with strict access controls
-- ENCRYPTED fields use AES-256-GCM; encryption keys are managed via a centralized KMS with regular key rotation.
CREATE TABLE phi_schema.member_identities (
    member_id TEXT PRIMARY KEY REFERENCES public.members(id),
    full_name TEXT ENCRYPTED,
    phone_number TEXT ENCRYPTED,
    date_of_birth DATE ENCRYPTED,
    emergency_contact TEXT ENCRYPTED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Consent Management
```sql
CREATE TABLE consents (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    member_id TEXT NOT NULL REFERENCES members(id),
    grantee_type TEXT NOT NULL CHECK (grantee_type IN ('clinician', 'family')),
    scope TEXT NOT NULL, -- JSON array of permissions
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE sharing_grants (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    member_id TEXT NOT NULL REFERENCES members(id),
    consent_id TEXT NOT NULL REFERENCES consents(id),
    family_contact_hash TEXT NOT NULL, -- Hashed phone/email for revocable access
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Clinical Data
```sql
CREATE TABLE check_ins (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    adherence INTEGER NOT NULL CHECK (adherence >= 0 AND adherence <= 100),
    mood_trend INTEGER NOT NULL CHECK (mood_trend >= -10 AND mood_trend <= 10),
    cravings INTEGER NOT NULL CHECK (cravings >= 0 AND cravings <= 100),
    sleep_hours DECIMAL(3,1) NOT NULL CHECK (sleep_hours >= 0 AND sleep_hours <= 24),
    isolation INTEGER NOT NULL CHECK (isolation >= 0 AND isolation <= 100),
    notes_redacted TEXT, -- Server-side redacted free text
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE risk_scores (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    score INTEGER CHECK (score >= 0 AND score <= 100), -- NULL for "no_data"
    band TEXT CHECK (band IN ('low', 'elevated', 'moderate', 'high', 'no_data')),
    model_version TEXT NOT NULL,
    explanations JSONB, -- Feature contributions
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    kind TEXT NOT NULL CHECK (kind IN ('risk', 'safety', 'engagement')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved')),
    ack_by TEXT REFERENCES clinicians(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Communication
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    member_id TEXT NOT NULL REFERENCES members(id),
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    template_key TEXT, -- For outbound templated messages
    redacted_body TEXT, -- PHI-stripped content
    provider_id TEXT, -- External SMS provider message ID
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### System Tables
```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT REFERENCES accounts(id),
    actor_id TEXT, -- Clinician or system
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    ip_hash TEXT, -- Hashed IP for privacy
    request_id TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- NO updates allowed - append only
);

CREATE TABLE feature_flags (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT REFERENCES accounts(id), -- NULL for global flags
    flag_key TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    rollout_percentage INTEGER DEFAULT 0 CHECK (rollout_percentage >= 0 AND rollout_percentage <= 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Data Layer Patterns

### 1. De-identified by Default
- Primary tables use `display_code` for member identification
- No names, phones, or PII in main schema
- Optional PHI lives in separate schema/database with encryption at rest
- Access to PHI gated by explicit consent records

### 2. Row-Level Security (RLS)
```sql
-- Enable RLS on all tenant tables
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE check_ins ENABLE ROW LEVEL SECURITY;

-- Policies ensure account isolation
CREATE POLICY account_isolation ON members
    FOR ALL TO application_role
    USING (account_id = current_setting('app.account_id'));
```

### 3. Soft Deletion & Immutability
- All tables include `deleted_at` for soft deletion
- `audit_logs` table is append-only (no updates/deletes)
- Critical data (check-ins, risk scores) are immutable after creation

### 4. Reliable Side Effects (Outbox Pattern)
```sql
CREATE TABLE outbox_events (
    id TEXT PRIMARY KEY DEFAULT generate_ulid(),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ NULL
);
```

### 5. Migration Strategy
- **Alembic** with linear history
- **Autogenerate disabled** by default - all migrations hand-reviewed
- SQL changes reviewed for performance impact
- Backward compatibility for 2+ versions

### 6. Technical Standards
- **IDs**: ULIDs (sortable, less timing leakage than UUID1)
- **Timestamps**: UTC only, `created_at`/`updated_at` everywhere
- **Pydantic v2**: Response DTOs mirror SQLAlchemy models
- **Grace Period**: Formal "no_data" state for <3 check-ins or <N days

### 7. Privacy Safeguards
```python
# Example: Privacy-safe member lookup
class MemberResponse(BaseModel):
    id: str
    display_code: str
    state: str
    created_at: datetime
    # Never include PHI in standard responses

# PHI access requires explicit consent check
async def get_member_phi(member_id: str, requester_id: str) -> Optional[MemberPHI]:
    consent = await check_phi_consent(member_id, requester_id)
    if not consent:
        return None
    return await fetch_member_phi(member_id)
```