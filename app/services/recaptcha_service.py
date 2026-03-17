# ============================================
# Service - Google reCAPTCHA Verification
# ============================================

from __future__ import annotations

import ipaddress

import structlog
from httpx import AsyncClient
from app.config import settings

logger = structlog.get_logger()

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def verify_recaptcha_token(token: str, remote_ip: str | None = None) -> dict:
    """
    Verify a reCAPTCHA token with Google's verification API.
    
    Args:
        token: The reCAPTCHA token from the frontend (v2 or v3)
        remote_ip: Optional client's IP address
        
    Returns:
        dict: Response from Google including 'success', 'challenge_ts', 'hostname', 
              and 'score' (for v3)
              
    Raises:
        Exception: If verification fails or secret key not configured
    """
    if not settings.RECAPTCHA_SECRET_KEY:
        logger.warning("recaptcha_secret_key_not_configured")
        raise ValueError("reCAPTCHA secret key not configured")
    
    if not token:
        logger.warning("recaptcha_token_missing")
        raise ValueError("reCAPTCHA token is missing")
    
    payload = {
        "secret": settings.RECAPTCHA_SECRET_KEY,
        "response": token,
    }
    
    # Google's `remoteip` field is optional. In local/dev environments the
    # request IP is often loopback/private (e.g. 127.0.0.1 via proxy), which
    # can cause verification mismatches. Only send globally routable IPs.
    if remote_ip:
        try:
            parsed_ip = ipaddress.ip_address(remote_ip)
            if parsed_ip.is_global:
                payload["remoteip"] = remote_ip
        except ValueError:
            # Ignore malformed IP and continue verification without remoteip.
            pass
    
    try:
        async with AsyncClient(timeout=10.0) as client:
            response = await client.post(RECAPTCHA_VERIFY_URL, data=payload)
            response.raise_for_status()
            result = response.json()
            
            logger.info(
                "recaptcha_verification",
                success=result.get("success"),
                score=result.get("score"),
                action=result.get("action"),
                error_codes=result.get("error-codes"),
            )
            
            return result
    except Exception as e:
        logger.error("recaptcha_verification_failed", error=str(e))
        raise


async def is_valid_recaptcha(token: str, remote_ip: str | None = None) -> bool:
    """
    Check if reCAPTCHA token is valid.
    
    For v3 tokens, also checks if score is above minimum threshold.
    
    Args:
        token: The reCAPTCHA token
        remote_ip: Optional client's IP address
        
    Returns:
        bool: True if token is valid and passes checks, False otherwise
    """
    if not settings.RECAPTCHA_ENABLED:
        return True
    
    try:
        result = await verify_recaptcha_token(token, remote_ip)
        
        # Check if verification was successful
        if not result.get("success"):
            logger.warning(
                "recaptcha_verification_failed_success_false",
                error_codes=result.get("error-codes"),
                hostname=result.get("hostname"),
            )
            return False
        
        # For v3, check score if present
        if "score" in result:
            score = result.get("score", 0)
            if score < settings.RECAPTCHA_MIN_SCORE:
                logger.warning(
                    "recaptcha_score_too_low",
                    score=score,
                    min_score=settings.RECAPTCHA_MIN_SCORE,
                )
                return False
        
        return True
    except Exception as e:
        logger.error("recaptcha_validation_exception", error=str(e))
        return False
