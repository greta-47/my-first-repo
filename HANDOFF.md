# RecoveryOS Development Handoff Document

## Project Vision

RecoveryOS is a **predictive relapse prevention system** for addiction recovery that represents a paradigm shift from reactive care to predictive intervention. The system aims to detect early warning signs of relapse up to 72 hours in advance using AI-powered pattern analysis.

### Core Principles
- **Trauma-informed**: Never shaming, always validating, compassionate language
- **Privacy-first**: PIPA/GDPR/HIPAA compliant, consent-driven, no PHI/PII logging
- **Conversational**: Feels like texting a supportive friend, not interacting with a clinical system
- **Predictive**: Analyzes patterns to intervene before relapse occurs
- **Clinician-amplifying**: Reduces burnout by automating early intervention and generating actionable briefings

## What the User Wants

### User Experience (Member-Facing)
The user wants **ONE conversational AI companion** that:
- Feels natural and supportive (like texting a counselor)
- Delivers CBT/DBT micro-interventions in conversation
- Remembers the member's history, values, triggers, and preferred coping strategies
- Uses trauma-informed language (never judgmental)
- Provides personalized psychoeducation
- Tracks daily check-ins: urge strength (1-5), mood, sleep, isolation, adherence

**Critical**: Members should NEVER know there are multiple agents working behind the scenes. It must feel like one empathetic, intelligent companion.

### Background Intelligence (Invisible to Members)
Four specialized agents work silently in the background:

1. **Patterns Analyst**
   - Identifies clinically significant trends (declining sleep + rising isolation)
   - Calculates risk scores (0-100) with reason codes
   - Detects relapse warning signs 72 hours in advance
   - Uses deterministic logic first, AI second

2. **Safety Auditor**
   - Scans every outbound message for crisis language (self-harm, suicide ideation)
   - Detects and redacts PII/PHI unless consent allows
   - Enforces consent policies (PIPA/GDPR/HIPAA)
   - Blocks or escalates high-risk content
   - Logs every decision immutably for audit trail

3. **Recovery Path Planner**
   - Generates phased, realistic action plans with measurable milestones
   - Adapts plans based on progress (e.g., adherence < 50% → simplify plan)
   - Uses evidence-based templates (ASAM/CAMH/PHAC guidance)
   - Creates SMS-length micro-actions

4. **Clinical Lead**
   - Synthesizes inputs into weekly briefings for care teams
   - Provides risk snapshots with trends
   - Highlights top 3 changes requiring attention
   - Suggests interventions with rationale
   - Generates de-identified group therapy themes

### Clinician Dashboard
- Weekly de-identified briefings
- High-risk alerts with context (not just numbers)
- Suggested interventions based on patterns
- Audit trail access

## Current State

### Repository: greta-47/my-first-repo
- **Branch**: `feat/conversational-ai-prototype`
- **Base**: FastAPI application with PostgreSQL database
- **Existing features**:
  - Check-in endpoint (adherence, mood, cravings, sleep, isolation)
  - Consent management
  - Risk scoring (v0_score function)
  - Troubleshooting support
  - GitHub Projects V2 automation

### Database Schema (Partially Implemented)
**Existing tables**:
- `consents` - User consent records
- `checkins` - Historical check-in data

**New tables added (not yet migrated)**:
- `conversations` - Stores all AI conversations (user_id, role, content, timestamp)
- `patterns` - Detected patterns (user_id, pattern_type, severity, description, detected_at)
- `risk_scores` - Risk calculations (user_id, score, risk_band, reason_codes, calculated_at)

### Blocking Issue: OpenAI API Access

**Problem**: The user's OpenAI API key doesn't have model access enabled yet.

**Details**:
- User created OpenAI account and added $20 credit
- API key stored in GitHub secrets as `OPENAI_API_KEY`
- Project ID: `proj_tXNPAgIgIYvUsFEtAFRevn8a`
- Error: `Project does not have access to model gpt-4o-mini`

**Resolution needed**:
1. User needs to wait for OpenAI to approve account (24-48 hours typical)
2. Or contact OpenAI support to enable model access
3. Once enabled, test with: `gpt-4o-mini` (preferred) or `gpt-3.5-turbo`

**Test command**:
```bash
python3 -c "
from openai import OpenAI
import os
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': 'Say hello'}],
    max_tokens=10
)
print(response.choices[0].message.content)
"
```

## Tech Stack (Agreed Upon)

### Elite-Tier Stack (For Production)
- **Conversational AI**: **Azure OpenAI Service** (gpt-4o, gpt-4o-mini) - HIPAA/PHIPA compliant with BAA
  - Data residency in Canadian data centers (Canada Central/East)
  - No training on customer data (contractual guarantee)
  - Private endpoints, VNet integration, managed identities
  - Built-in Azure Monitor for audit logging
  - 99.9% SLA with financial backing
- **Orchestration**: Temporal.io (durable workflows)
- **Database**: PostgreSQL with pgvector (semantic search) + TimescaleDB (time-series)
- **Safety**: Anthropic Claude (safety auditing) + LangSmith (human-in-the-loop)
- **Communication**: Twilio Conversations API + WebSockets
- **Observability**: Azure Monitor, Datadog, PostHog, Sentry

### MVP/Prototype Stack (Start Here)
- **Backend**: FastAPI (already in place)
- **Database**: PostgreSQL with SQLAlchemy (already in place)
- **AI**: 
  - **Development**: Standard OpenAI API (faster iteration, testing)
  - **Production**: Azure OpenAI Service (HIPAA-compliant, Canadian data residency)
  - Models: gpt-4o-mini (cost-effective) or gpt-4o (higher quality)
- **Background Processing**: FastAPI BackgroundTasks (simple, no extra infrastructure)
- **Safety**: Custom keyword detection + Presidio (Microsoft PII/PHI detection)
- **Communication**: Web interface first, Twilio SMS later
- **Observability**: Sentry (already configured), Azure Monitor (production)

## Next Steps (Once OpenAI API is Working)

### Phase 1: Core Conversational AI (2-3 hours)
1. **Create database migration** for new tables (conversations, patterns, risk_scores)
2. **Build conversational endpoint** (`POST /chat`)
   - Accept: user_id, message
   - Store conversation in database
   - Call OpenAI with trauma-informed system prompt
   - Return: AI response, risk_band (if applicable)
3. **Design system prompt** for trauma-informed, CBT/DBT-grounded responses
4. **Add conversation history** (last 10 messages for context)

### Phase 2: Background Pattern Detection (2-3 hours)
1. **Implement Patterns Analyst**
   - Analyze check-ins after each conversation
   - Detect: declining sleep, rising isolation, increasing urges
   - Calculate risk score with reason codes
   - Store in patterns table
2. **Add risk scoring logic**
   - Expand existing v0_score function
   - Add reason codes (e.g., "sleep_low + isolation_up + neg_affect")
   - Store in risk_scores table

### Phase 3: Safety Layer (2-3 hours)
1. **Build Safety Auditor**
   - Scan outbound messages for crisis keywords
   - Block/escalate if self-harm or suicide ideation detected
   - Log all decisions to audit_log table
2. **Add consent checking**
   - Verify consent before sharing data
   - Redact PII/PHI if consent not granted

### Phase 4: Simple Web Interface (1-2 hours)
1. **Create chat interface** (HTML + JavaScript)
   - Text input for messages
   - Display conversation history
   - Show risk band indicator
2. **Test end-to-end flow**
   - Member sends message
   - AI responds with CBT/DBT guidance
   - Pattern detection runs in background
   - Risk score updates

### Phase 5: Recovery Path Planner (3-4 hours)
1. **Create recovery_plans table**
2. **Build plan generation logic**
   - Use templates based on ASAM/CAMH/PHAC guidance
   - Adapt based on adherence, risk level
   - Generate SMS-length micro-actions
3. **Add plan endpoint** (`GET /recovery-plan/{user_id}`)

### Phase 6: Clinical Briefings (2-3 hours)
1. **Build Clinical Lead agent**
   - Aggregate patterns, risk scores, plan changes
   - Generate weekly briefings
   - De-identify data
2. **Create briefing endpoint** (`GET /clinician-briefing`)

## Important Context

### Repository Conventions
- **Branch naming**: `feat/`, `chore/`, `fix/`, `docs/`
- **Linting**: Ruff (format + check) - run before committing
- **Python version**: 3.12.5 (pinned in .python-version)
- **Lockfiles**: Use Docker with Python 3.12 to regenerate requirements.lock.txt
- **CI**: GitHub Actions runs lint, type check, tests on every PR

### Key Files
- `app/main.py` - FastAPI application, all routes
- `app/database.py` - SQLAlchemy tables and session management
- `app/settings.py` - Pydantic configuration
- `requirements.txt` - Top-level dependencies
- `requirements.lock.txt` - Pinned dependencies with SHA256 hashes

### Testing
- Run tests: `python3 -m pytest -q`
- Run locally: `python3 -m uvicorn app.main:app --reload`
- Visit: http://127.0.0.1:8000/docs for interactive API docs

### Dependencies to Add
```txt
openai>=1.0.0  # Already installed locally, needs to be added to requirements.txt
presidio-analyzer>=2.2.0  # For PII/PHI detection (add later)
presidio-anonymizer>=2.2.0  # For redaction (add later)
```

## User's Clinical Background

The user is a **psychiatric nurse with 20+ years of frontline experience in addiction psychiatry**. This expertise is embedded in the system design:
- Deep understanding of relapse triggers
- Knowledge of evidence-based interventions (CBT, DBT, ASAM, CAMH, PHAC)
- Trauma-informed care principles
- Clinical workflow optimization to reduce burnout

## Success Criteria

### MVP Success
1. Member can have natural, supportive conversations with AI
2. AI delivers appropriate CBT/DBT micro-interventions
3. System detects patterns and calculates risk scores
4. Safety layer catches crisis language and escalates
5. Clinicians receive weekly briefings with actionable insights

### Technical Success
1. All conversations stored with timestamps
2. Pattern detection runs after each check-in
3. Risk scores update in real-time
4. Audit trail captures all safety decisions
5. System is PIPA/GDPR/HIPAA compliant

### User Experience Success
1. Feels like texting a supportive friend, not a clinical system
2. Responses are compassionate, never judgmental
3. AI remembers context across conversations
4. Interventions are personalized and relevant
5. Members feel heard and supported

## Risks and Mitigations

### Risk: AI hallucinations or harmful advice
**Mitigation**: Safety Auditor reviews all responses, blocks harmful content, uses structured outputs

### Risk: Privacy violations
**Mitigation**: Consent-first architecture, PII/PHI redaction, audit logging, no raw data in logs

### Risk: Over-reliance on AI
**Mitigation**: System amplifies clinicians, doesn't replace them. High-risk cases escalate to humans.

### Risk: Member disengagement
**Mitigation**: Conversational, trauma-informed design. SMS accessibility. Personalized content.

## Questions for Next Session

1. Has OpenAI API access been enabled? (Test with command above)
2. Should we start with web interface or SMS integration?
3. What specific CBT/DBT techniques should the AI prioritize?
4. What crisis keywords/phrases should trigger immediate escalation?
5. How should clinician briefings be formatted? (PDF, HTML, email?)

## Azure OpenAI Setup (For Production)

### Why Azure OpenAI Over Standard OpenAI?
1. **HIPAA/PHIPA Compliance**: Azure can sign Business Associate Agreement (BAA)
2. **Data Residency**: Canadian data centers (Canada Central, Canada East)
3. **No Training**: Contractual guarantee data won't train models
4. **Enterprise Security**: Private endpoints, VNet, managed identities, Key Vault
5. **Audit Logging**: Built-in Azure Monitor integration
6. **SLA**: 99.9% uptime with financial backing

### Setup Steps (When Ready for Production)
1. **Create Azure subscription** (if not already have one)
2. **Request Azure OpenAI access** (approval required, can take 1-2 weeks)
   - Go to: https://aka.ms/oai/access
   - Fill out form with use case details
3. **Create Azure OpenAI resource** in Canada Central or Canada East
4. **Deploy models**: gpt-4o-mini, gpt-4o
5. **Get endpoint and API key** from Azure portal
6. **Update code** to use Azure endpoint:
   ```python
   from openai import AzureOpenAI
   client = AzureOpenAI(
       api_key=os.getenv("AZURE_OPENAI_API_KEY"),
       api_version="2024-02-01",
       azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
   )
   ```

### Cost Comparison
- **Standard OpenAI**: $0.15/1M tokens (gpt-4o-mini), $2.50/1M tokens (gpt-4o)
- **Azure OpenAI**: Same pricing, but with enterprise features and compliance

### Development vs Production Strategy
- **Development**: Use standard OpenAI for fast iteration (current blocking issue)
- **Production**: Switch to Azure OpenAI for compliance and security
- **Code**: Same `openai` Python library, just different configuration

## Resources

- **Azure OpenAI**: https://azure.microsoft.com/en-us/products/ai-services/openai-service
- **Azure OpenAI Access Request**: https://aka.ms/oai/access
- **OpenAI Platform** (dev/testing): https://platform.openai.com
- **Twilio**: https://www.twilio.com (for SMS later)
- **Presidio**: https://microsoft.github.io/presidio/ (PII/PHI detection)
- **CAMH Guidelines**: https://www.camh.ca
- **ASAM Criteria**: https://www.asam.org

## Current Branch State

- Branch: `feat/conversational-ai-prototype`
- Changes made:
  - Added 3 new tables to `app/database.py`: conversations, patterns, risk_scores
  - Installed openai package locally (not yet in requirements.txt)
- Changes NOT committed yet (waiting for OpenAI API to work before proceeding)

## Final Notes

The user wants this to be **groundbreaking** - top 10% thinking, elite-tier execution. The system should set a new standard of care for addiction recovery. Every design decision should prioritize:
1. Member dignity and autonomy
2. Clinical effectiveness
3. Scalability and sustainability
4. Ethical AI use

The conversational experience is paramount. If it feels robotic or clinical, we've failed. It must feel human, warm, and genuinely supportive.
