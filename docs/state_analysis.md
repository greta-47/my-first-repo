# Deep Dive: State Management & Data Flow Analysis

## In-Memory Data Stores Inventory

### 1. `RATE_LIMIT.hits: Dict[str, Deque[float]]`
**Location:** Line 83, inside `InMemoryRateLimiter` class
**Purpose:** Track request timestamps per anonymous client key

**Read Operations:**
- [`rate_limit_middleware`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L557) → `RATE_LIMIT.allow()` → reads `self.hits[key]`

**Write Operations:**
- [`rate_limit_middleware`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L557) → `RATE_LIMIT.allow()` → `dq.append(now)`

**Modify Operations:**
- [`InMemoryRateLimiter.allow()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L89-L90) → `dq.popleft()` (removes expired timestamps)

### 2. `CONSENTS: Dict[str, ConsentRecord]`
**Location:** Line 98
**Purpose:** Store user consent records by user_id

**Read Operations:**
- [`get_consents()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L626) → `CONSENTS.get(user_id)`

**Write Operations:**
- [`post_consents()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L619) → `CONSENTS[payload.user_id] = rec`

**Modify Operations:**
- None (only overwrites entire records)

### 3. `CHECKINS: Dict[str, List[CheckIn]]`
**Location:** Line 99 (defaultdict)
**Purpose:** Store check-in history per user_id

**Read Operations:**
- [`check_in()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L641) → `history = CHECKINS[payload.user_id]`
- [`metrics()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L589) → `sum(len(v) for v in CHECKINS.values())`

**Write Operations:**
- [`check_in()`](https://recoveryos.sourcegraph.app/github.com/greta-47/my-first-repo/-/blob/app/main.py?L640) → `CHECKINS[payload.user_id].append(payload)`

**Modify Operations:**
- Only appends (never deletes or modifies existing check-ins)

## Complete Data Flow: POST /check-in

### Phase 1: Request Entry & Rate Limiting
```python
# 1. HTTP Request arrives
POST /check-in
Content-Type: application/json
{
  "user_id": "user123",
  "adherence": 85,
  "mood_trend": 2,
  "cravings": 15,
  "sleep_hours": 7.5,
  "isolation": 20
}

# 2. Middleware intercepts
@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    if request.method == "POST" and request.url.path == "/check-in":
        # SIDE EFFECT: Extract IP/UA from request
        key = get_rate_key(request)  # Creates anonymous hash
        
        # READ/WRITE: Rate limiter state
        if not RATE_LIMIT.allow(key):
            # SIDE EFFECT: Log rate limit hit
            logger.info("rate_limited")
            return 429_error_response
```

### Phase 2: Input Validation
```python
# 3. FastAPI + Pydantic validation
async def check_in(payload: CheckIn, response: Response):
    # Automatic validation of:
    # - user_id: min_length=1
    # - adherence: 0 <= x <= 100
    # - mood_trend: -10 <= x <= 10
    # - cravings: 0 <= x <= 100
    # - sleep_hours: 0 <= x <= 24
    # - isolation: 0 <= x <= 100
```

### Phase 3: Storage & Business Logic
```python
# 4. WRITE: Append to user's check-in history
CHECKINS[payload.user_id].append(payload)  # Thread-unsafe!

# 5. READ: Get full history for scoring
history = CHECKINS[payload.user_id]  # Could be stale read

# 6. Business rule check
if len(history) < 3:
    # SIDE EFFECT: Log insufficient data
    logger.info("insufficient_data")
    return CheckInResponse(state="insufficient_data")
```

### Phase 4: Risk Scoring
```python
# 7. Pure calculation (no side effects)
score, reflection, footer = v0_score(history)

# v0_score algorithm:
def v0_score(checkins: List[CheckIn]) -> Tuple[int, str, str]:
    latest = checkins[-1]  # Uses only latest check-in
    score = 0
    score += max(0, 100 - latest.adherence) // 4      # 0-25 points
    score += max(0, -latest.mood_trend) * 3           # 0-30 points  
    score += latest.cravings // 3                     # 0-33 points
    score += int(max(0.0, 8.0 - latest.sleep_hours) * 4)  # 0-32 points
    score += latest.isolation // 2                    # 0-50 points
    score = max(0, min(100, score))                   # Clamp 0-100
```

### Phase 5: Response Generation
```python
# 8. Determine risk band
if score < 30: band = "low"
elif score < 55: band = "elevated" 
elif score < 75: band = "moderate"
else: band = "high"

# 9. SIDE EFFECT: Privacy-safe logging
logger.info("check_in_scored", json.dumps({
    "user": "redacted", 
    "band": band, 
    "score": score
}))

# 10. Return structured response
return CheckInResponse(
    state="ok",
    band=band,
    score=score,
    reflection=reflection,
    footer=footer
)
```

## Side Effects & Shared Mutable State

### Side Effects Identified:
1. **Logging calls** - `logger.info()` throughout the flow
2. **Timestamp generation** - `iso_now()` in consent creation
3. **Request metadata extraction** - IP/UA hashing for rate limiting
4. **Global state mutation** - All dictionary modifications

### Shared Mutable State Risks:
1. **`CHECKINS` dictionary** - Concurrent appends could cause data races
2. **`CONSENTS` dictionary** - Concurrent writes could lose data
3. **Rate limiter deques** - Concurrent modifications could corrupt state

## Race Conditions & Thread Safety Risks

### 🚨 Critical Race Conditions:

#### 1. Check-in History Race
```python
# Thread A and B both POST for same user simultaneously:
# Thread A: CHECKINS[user_id].append(checkin_A)  
# Thread B: CHECKINS[user_id].append(checkin_B)
# Thread A: history = CHECKINS[user_id]  # May miss checkin_B
# Thread B: history = CHECKINS[user_id]  # May miss checkin_A
```

#### 2. Rate Limiter Race
```python
# Thread A and B with same IP/UA:
# Thread A: dq = self.hits[key]        # Gets deque reference
# Thread B: dq = self.hits[key]        # Gets same deque reference  
# Thread A: dq.append(now_A)           # Modifies deque
# Thread B: dq.append(now_B)           # Concurrent modification!
```

#### 3. Consent Overwrite Race
```python
# Thread A: CONSENTS[user_id] = consent_A
# Thread B: CONSENTS[user_id] = consent_B  # Overwrites A's consent
```

### Thread Safety Issues:
- **Python GIL** provides some protection but not full thread safety
- **defaultdict** operations are not atomic
- **deque** operations are not thread-safe for concurrent modifications
- **Dictionary assignments** can be lost in race conditions

## Service Layer vs API Handler Separation

### Current Mixing of Concerns:
```python
# ❌ API Handler doing everything:
async def check_in(payload: CheckIn, response: Response):
    CHECKINS[payload.user_id].append(payload)      # Data access
    history = CHECKINS[payload.user_id]            # Data access  
    if len(history) < 3:                           # Business logic
        return CheckInResponse(state="insufficient_data")  # Response
    score, reflection, footer = v0_score(history)  # Business logic
    # ... more business logic and response building
```

### Recommended Separation:

#### **Should Stay in API Handlers:**
- Request/response serialization
- HTTP status code determination  
- Error response formatting
- Request validation (Pydantic)
- Authentication/authorization checks

#### **Should Move to Service Layer:**
```python
# ✅ Proposed Service Layer
class CheckInService:
    def __init__(self, repo: CheckInRepository):
        self.repo = repo
    
    async def process_checkin(self, user_id: str, checkin: CheckIn) -> CheckInResult:
        # Business logic only
        await self.repo.save_checkin(user_id, checkin)
        history = await self.repo.get_user_history(user_id)
        
        if len(history) < 3:
            return CheckInResult(state="insufficient_data")
            
        score, reflection, footer = self.calculate_risk_score(history)
        return CheckInResult(
            state="ok", 
            score=score, 
            band=self.determine_band(score),
            reflection=reflection,
            footer=footer
        )

# ✅ Clean API Handler  
async def check_in(payload: CheckIn) -> CheckInResponse:
    try:
        result = await checkin_service.process_checkin(payload.user_id, payload)
        return CheckInResponse.from_result(result)
    except InsufficientDataError:
        return CheckInResponse(state="insufficient_data")
    except Exception as e:
        return create_error_response("internal-error", str(e))
```

#### **Should Move to Repository Layer:**
```python
class CheckInRepository:
    async def save_checkin(self, user_id: str, checkin: CheckIn) -> None:
        # Data persistence logic
        
    async def get_user_history(self, user_id: str) -> List[CheckIn]:
        # Data retrieval logic
        
    async def get_checkin_count(self) -> int:
        # Metrics logic
```

## PostgreSQL Migration Breaking Points

### 🚨 What Would Break Tomorrow:

#### 1. **Synchronous to Async Data Access**
```python
# Current (synchronous):
CHECKINS[payload.user_id].append(payload)
history = CHECKINS[payload.user_id]

# PostgreSQL (async required):
await db.execute("INSERT INTO checkins ...")
history = await db.fetch_all("SELECT * FROM checkins WHERE user_id = $1", user_id)
```

#### 2. **Transaction Boundaries Missing**
```python
# Current (no transactions):
CHECKINS[user_id].append(checkin)  # Always succeeds
# If scoring fails, checkin is still stored

# PostgreSQL (needs transactions):
async with db.transaction():
    await save_checkin(checkin)
    score = calculate_score(await get_history(user_id))
    await save_risk_score(score)
    # All or nothing
```

#### 3. **Connection Pool Management**
```python
# Current (no connections):
# Direct memory access

# PostgreSQL (connection required):
async def check_in(payload: CheckIn, db: Database = Depends(get_db)):
    # Every operation needs database connection
```

#### 4. **Error Handling Explosion**
```python
# Current (no database errors):
# Memory operations rarely fail

# PostgreSQL (many failure modes):
try:
    await db.execute(...)
except ConnectionError:
    # Database down
except IntegrityError: 
    # Constraint violation
except TimeoutError:
    # Query too slow
except Exception:
    # Unknown database error
```

#### 5. **Metrics Collection**
```python
# Current (direct access):
f"app_checkins_total {sum(len(v) for v in CHECKINS.values())}"

# PostgreSQL (query required):
count = await db.fetch_val("SELECT COUNT(*) FROM checkins")
f"app_checkins_total {count}"
```

### Required Changes for PostgreSQL:

#### **1. Database Configuration**
```python
from databases import Database
from sqlalchemy import create_engine

DATABASE_URL = "postgresql://user:pass@localhost/recoveryos"
database = Database(DATABASE_URL)
engine = create_engine(DATABASE_URL)
```

#### **2. Schema Definitions**
```python
import sqlalchemy as sa

checkins_table = sa.Table(
    "checkins",
    sa.MetaData(),
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, nullable=False),
    sa.Column("adherence", sa.Integer, nullable=False),
    sa.Column("mood_trend", sa.Integer, nullable=False),
    sa.Column("cravings", sa.Integer, nullable=False),
    sa.Column("sleep_hours", sa.Float, nullable=False),
    sa.Column("isolation", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime, nullable=False),
)
```

#### **3. Repository Pattern Implementation**
```python
class PostgreSQLCheckInRepository:
    def __init__(self, db: Database):
        self.db = db
    
    async def save_checkin(self, user_id: str, checkin: CheckIn) -> None:
        query = checkins_table.insert().values(
            id=generate_ulid(),
            user_id=user_id,
            adherence=checkin.adherence,
            mood_trend=checkin.mood_trend,
            cravings=checkin.cravings,
            sleep_hours=checkin.sleep_hours,
            isolation=checkin.isolation,
            created_at=datetime.utcnow()
        )
        await self.db.execute(query)
    
    async def get_user_history(self, user_id: str) -> List[CheckIn]:
        query = checkins_table.select().where(
            checkins_table.c.user_id == user_id
        ).order_by(checkins_table.c.created_at.desc())
        rows = await self.db.fetch_all(query)
        return [CheckIn.from_row(row) for row in rows]
```

#### **4. Dependency Injection**
```python
async def get_database() -> Database:
    return database

async def get_checkin_service(db: Database = Depends(get_database)) -> CheckInService:
    repo = PostgreSQLCheckInRepository(db)
    return CheckInService(repo)

@app.post("/check-in")
async def check_in(
    payload: CheckIn, 
    service: CheckInService = Depends(get_checkin_service)
) -> CheckInResponse:
    result = await service.process_checkin(payload.user_id, payload)
    return CheckInResponse.from_result(result)
```

#### **5. Migration Strategy**
```python
# Gradual migration approach:
class HybridCheckInRepository:
    def __init__(self, db: Database, fallback_to_memory: bool = True):
        self.db = db
        self.fallback = fallback_to_memory
    
    async def save_checkin(self, user_id: str, checkin: CheckIn) -> None:
        try:
            await self._save_to_postgres(user_id, checkin)
        except Exception as e:
            if self.fallback:
                logger.warning(f"DB save failed, using memory: {e}")
                CHECKINS[user_id].append(checkin)
            else:
                raise
```

The current architecture's simplicity is both its strength (easy to understand) and weakness (not production-ready). The transition to PostgreSQL will require comprehensive refactoring of data access patterns, error handling, and architectural separation of concerns. 
