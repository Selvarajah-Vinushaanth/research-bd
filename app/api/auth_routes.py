# ============================================
# API Routes - Authentication
# ============================================

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.database.prisma_client import get_db
from app.middleware.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.schemas.user_schema import (
    PasswordChangeRequest,
    TokenRefreshRequest,
    TokenResponse,
    UserLoginRequest,
    UserProfileResponse,
    UserRegisterRequest,
    UserUpdateRequest,
)
from app.services.recaptcha_service import is_valid_recaptcha

logger = structlog.get_logger()
router = APIRouter()


@router.post("/register", response_model=UserProfileResponse, status_code=status.HTTP_201_CREATED)
async def register(request: UserRegisterRequest, http_request: Request):
    """
    Register a new user account.
    
    Validates email uniqueness, password strength, and reCAPTCHA token.
    """
    # Verify reCAPTCHA token
    client_ip = http_request.client.host if http_request.client else None
    is_valid = await is_valid_recaptcha(request.recaptcha_token, client_ip)
    if not is_valid:
        logger.warning("registration_recaptcha_verification_failed", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reCAPTCHA verification failed",
        )
    
    db = get_db()

    # Check if email already exists
    existing = await db.user.find_unique(where={"email": request.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    hashed = hash_password(request.password)
    user = await db.user.create(
        data={
            "email": request.email,
            "password": hashed,
            "name": request.name,
            "institution": request.institution,
            "research_areas": request.research_areas,
        }
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "USER_REGISTERED",
            "resource": "user",
            "resource_id": user.id,
        }
    )

    logger.info("user_registered", user_id=user.id, email=user.email)

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        institution=user.institution,
        research_areas=user.research_areas,
        role=user.role,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLoginRequest, http_request: Request):
    """
    Authenticate a user and return JWT tokens.
    
    Verifies reCAPTCHA token before processing login.
    """
    # Verify reCAPTCHA token
    client_ip = http_request.client.host if http_request.client else None
    is_valid = await is_valid_recaptcha(request.recaptcha_token, client_ip)
    if not is_valid:
        logger.warning("login_recaptcha_verification_failed", email=request.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reCAPTCHA verification failed",
        )
    
    db = get_db()

    user = await db.user.find_unique(where={"email": request.email})
    if not user or not verify_password(request.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Generate tokens
    access_token = create_access_token(data={"sub": user.id, "email": user.email})
    refresh_token = create_refresh_token(data={"sub": user.id})

    # Update last login
    await db.user.update(
        where={"id": user.id},
        data={"last_login": datetime.now(timezone.utc)},
    )

    # Log activity
    await db.activitylog.create(
        data={
            "user_id": user.id,
            "action": "USER_LOGIN",
            "resource": "auth",
        }
    )

    logger.info("user_logged_in", user_id=user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: TokenRefreshRequest):
    """
    Refresh an access token using a valid refresh token.
    """
    payload = decode_token(request.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    db = get_db()
    user = await db.user.find_unique(where={"id": user_id})

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )

    access_token = create_access_token(data={"sub": user.id, "email": user.email})
    new_refresh_token = create_refresh_token(data={"sub": user.id})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_profile(user=Depends(get_current_user)):
    """Get the current user's profile."""
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        institution=user.institution,
        research_areas=user.research_areas,
        role=user.role,
        is_active=user.is_active,
        last_login=user.last_login,
        created_at=user.created_at,
    )


@router.put("/me", response_model=UserProfileResponse)
async def update_profile(request: UserUpdateRequest, user=Depends(get_current_user)):
    """Update the current user's profile."""
    db = get_db()

    update_data = request.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    updated = await db.user.update(
        where={"id": user.id},
        data=update_data,
    )

    return UserProfileResponse(
        id=updated.id,
        email=updated.email,
        name=updated.name,
        institution=updated.institution,
        research_areas=updated.research_areas,
        role=updated.role,
        is_active=updated.is_active,
        last_login=updated.last_login,
        created_at=updated.created_at,
    )


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(request: PasswordChangeRequest, user=Depends(get_current_user)):
    """Change the current user's password."""
    if not verify_password(request.current_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    db = get_db()
    hashed = hash_password(request.new_password)
    await db.user.update(
        where={"id": user.id},
        data={"password": hashed},
    )

    logger.info("password_changed", user_id=user.id)
    return {"message": "Password changed successfully"}
