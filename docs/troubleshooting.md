# Troubleshooting Authentication and Access Issues

## Common Authentication Problems

### Cannot Access API Endpoints

If you're having trouble accessing the Single Compassionate Loop API endpoints, here are common causes and solutions:

#### 1. Network Connectivity Issues
- **Symptom**: Unable to connect to the API server
- **Solutions**:
  - Check your internet connection
  - Verify the API server is running on the correct port (default: 8000)
  - Test connectivity with: `curl -fsS http://127.0.0.1:8000/healthz`
  - Check if firewall or proxy settings are blocking requests

#### 2. Rate Limiting (HTTP 429)
- **Symptom**: Receiving "rate_limited" error with HTTP 429 status
- **Cause**: Too many requests from your client within the time window
- **Solutions**:
  - Wait for the rate limit window to reset (10 seconds)
  - Reduce request frequency to stay within limits (5 requests per 10 seconds)
  - Implement exponential backoff in your client code

#### 3. Invalid Request Format
- **Symptom**: HTTP 400 or 422 validation errors
- **Solutions**:
  - Ensure JSON payload matches the expected schema
  - Verify all required fields are included
  - Check data types and validation constraints
  - Review API documentation for endpoint requirements

#### 4. Server Not Running
- **Symptom**: Connection refused or timeout errors
- **Solutions**:
  - Start the server: `python -m uvicorn app.main:app --reload`
  - Check server logs for startup errors
  - Verify the correct port is being used
  - Ensure all dependencies are installed

## Endpoint-Specific Troubleshooting

### /check-in Endpoint Issues

#### Insufficient Data Response
- **Response**: `{"state": "insufficient_data"}`
- **Cause**: User has submitted fewer than 3 check-ins
- **Solution**: Submit at least 3 check-ins to receive scoring

#### Rate Limited Check-ins
- **Response**: HTTP 429 with `{"detail": "rate_limited"}`
- **Cause**: Exceeded 5 check-ins per 10-second window
- **Solution**: Space out check-in submissions

### /consents Endpoint Issues

#### User Not Found
- **Response**: `{"detail": "not_found"}`
- **Cause**: No consent record exists for the user_id
- **Solution**: Submit consent via POST /consents first

## Server Health Checks

Use these endpoints to verify server status:

### Health Check
```bash
curl http://127.0.0.1:8000/healthz
# Expected: "ok"
```

### Readiness Check
```bash
curl http://127.0.0.1:8000/readyz
# Expected: {"ok": true, "uptime_s": <seconds>}
```

### Metrics
```bash
curl http://127.0.0.1:8000/metrics
# Expected: Prometheus-style metrics
```

## Client Implementation Best Practices

### Error Handling
Implement proper error handling for common HTTP status codes:

```python
import httpx
import time
from typing import Optional

class APIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url
        self.client = httpx.Client()
    
    def submit_checkin(self, payload: dict) -> Optional[dict]:
        try:
            response = self.client.post(f"{self.base_url}/check-in", json=payload)
            
            if response.status_code == 429:
                print("Rate limited. Waiting before retry...")
                time.sleep(10)
                return self.submit_checkin(payload)  # Retry once
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP error: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            print(f"Request error: {e}")
            return None
```

### Retry Logic
Implement exponential backoff for transient failures:

```python
import random
import time

def exponential_backoff_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            
            wait_time = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(wait_time)
```

## Getting Help

If you continue to experience issues:

1. **Check server logs**: Look for JSON-formatted log entries for error details
2. **Verify request format**: Use API documentation to confirm payload structure
3. **Test with curl**: Isolate client-side vs server-side issues
4. **Check network**: Verify connectivity and proxy settings
5. **Review rate limits**: Ensure you're not exceeding request limits

## Privacy and Security Notes

- User identifiers are anonymized in logs for privacy protection
- Rate limiting uses hashed IP+User-Agent combinations
- No sensitive data is logged or exposed in error messages
- All logs are structured JSON without PHI/PII information

For development issues or bugs, please create an issue in the repository with:
- Error messages or logs
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Python version, etc.)