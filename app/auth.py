from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.settings import settings

security = HTTPBearer(auto_error=False)


class JWTValidator:
    def __init__(self):
        self._public_keys: Optional[Dict[str, Any]] = None
        self._keys_cached_at: float = 0.0

    async def get_public_keys(self) -> Dict[str, Any]:
        now = time.time()
        cache_age = now - self._keys_cached_at

        if self._public_keys is not None and cache_age < settings.jwt_keys_cache_ttl:
            return self._public_keys

        if not settings.jwt_public_keys_url:
            return {}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(str(settings.jwt_public_keys_url))
                response.raise_for_status()
                jwks = response.json()
                self._public_keys = {key["kid"]: key for key in jwks.get("keys", [])}
                self._keys_cached_at = now
                return self._public_keys
        except Exception:
            return {}

    async def validate_token(self, token: str) -> Dict[str, Any]:
        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            keys = await self.get_public_keys()
            if not keys:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="JWT validation not configured",
                )

            key = keys.get(kid)
            if not key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: unknown key ID"
                )

            payload = jwt.decode(
                token, key, algorithms=[settings.jwt_algorithm], options={"verify_aud": False}
            )
            return payload

        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}"
            )


jwt_validator = JWTValidator()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    """
    Get the current authenticated user from JWT token.

    Security Behavior:
    - When JWT validation is not configured (jwt_public_keys_url is None):
      Returns anonymous user for development/testing environments only.
      In production, always configure JWT validation to enforce authentication.
    - When JWT validation is configured but no credentials provided:
      Raises 401 Unauthorized exception.
    - When credentials are provided:
      Validates token and returns authenticated user information.

    Returns:
        Dict containing user_id, email (optional), authenticated status, and payload.

    Raises:
        HTTPException: 401 if credentials missing or invalid when JWT is configured.
        HTTPException: 503 if JWT validation service is unavailable.
    """
    if not settings.jwt_public_keys_url:
        return {"user_id": "anonymous", "authenticated": False}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = await jwt_validator.validate_token(credentials.credentials)
    return {
        "user_id": payload.get("sub", "unknown"),
        "email": payload.get("email"),
        "authenticated": True,
        "payload": payload,
    }


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Dict[str, Any]:
    if not credentials:
        return {"user_id": "anonymous", "authenticated": False}

    try:
        payload = await jwt_validator.validate_token(credentials.credentials)
        return {
            "user_id": payload.get("sub", "unknown"),
            "email": payload.get("email"),
            "authenticated": True,
            "payload": payload,
        }
    except HTTPException:
        return {"user_id": "anonymous", "authenticated": False}
