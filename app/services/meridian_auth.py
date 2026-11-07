"""Trusted server-to-server authentication requests; no model involvement."""
import os

import httpx
from fastapi import HTTPException


def backend_request(path, *, method="GET", body=None, authorization=None, legacy_key=None, params=None, allowed_error_detail=False, idempotency_key=None):
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    elif legacy_key:
        headers["X-API-Key"] = legacy_key
    if idempotency_key is not None:
        headers['Idempotency-Key'] = idempotency_key
    try:
        with httpx.Client(base_url=os.getenv("MERIDIAN_BACKEND_URL", "http://127.0.0.1:8000"), timeout=15, trust_env=False, follow_redirects=False) as client:
            result = client.request(method, path, json=body, headers=headers, params=params)
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Login service is unavailable") from None
    if result.status_code >= 400:
        status = result.status_code if result.status_code in {400, 401, 403, 404, 409, 422, 429} else 503
        detail = "Invalid or expired login" if status == 401 else "Authentication request could not be completed"
        if allowed_error_detail and status in {400, 403, 404, 409, 422}:
            try:
                message = result.json().get("detail")
                if isinstance(message, str):
                    detail = message[:500]
                elif status == 422:
                    detail = "Check the required fields and their values."
            except ValueError:
                pass
        raise HTTPException(status_code=status, detail=detail)
    if result.status_code == 204:
        return None
    try:
        return result.json()
    except ValueError:
        raise HTTPException(status_code=503, detail="Login service returned an invalid response") from None
