"""Auth API routes — register, login, logout, me, refresh, stats."""
from fastapi import APIRouter, Cookie, Request, Response
from pydantic import BaseModel, EmailStr, field_validator

from backend.app.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from backend.app.auth.users import AuthError, UserStore
from backend.app.api.errors import ApiError

COOKIE_OPTS = dict(httponly=True, samesite="lax", secure=False)  # set secure=True in prod with HTTPS


class RegisterIn(BaseModel):
    email: str
    name: str
    password: str

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or len(v) < 5:
            raise ValueError("Invalid email address")
        return v

    @field_validator("name")
    @classmethod
    def name_valid(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Name cannot be empty")
        return v

    @field_validator("password")
    @classmethod
    def pw_valid(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user["name"], "created_at": user["created_at"]}


def _set_tokens(response: Response, user_id: str, email: str) -> dict:
    access = create_access_token(user_id, email)
    refresh = create_refresh_token(user_id)
    response.set_cookie("cf_access", access, max_age=86400, **COOKIE_OPTS)
    response.set_cookie("cf_refresh", refresh, max_age=86400 * 30, **COOKIE_OPTS)
    return {"access_token": access, "token_type": "bearer"}


def make_auth_router(user_store: UserStore) -> APIRouter:
    router = APIRouter(prefix="/auth")

    def _current_user(request: Request) -> dict | None:
        """Extract user from cookie or Authorization header (for flexibility)."""
        token = request.cookies.get("cf_access")
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
        if not token:
            return None
        payload = decode_access_token(token)
        if not payload:
            return None
        return user_store.get_by_id(payload["sub"])

    @router.post("/register", status_code=201)
    def register(body: RegisterIn, response: Response):
        try:
            user = user_store.create_user(body.email, body.name, hash_password(body.password))
        except AuthError as e:
            raise ApiError(409, e.kind, str(e))
        tokens = _set_tokens(response, user["id"], user["email"])
        return {"user": _user_out(user), **tokens}

    @router.post("/login")
    def login(body: LoginIn, response: Response):
        user = user_store.get_by_email(body.email)
        if not user or not verify_password(body.password, user["hashed_password"]):
            raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
        tokens = _set_tokens(response, user["id"], user["email"])
        return {"user": _user_out(user), **tokens}

    @router.post("/logout")
    def logout(response: Response):
        response.delete_cookie("cf_access")
        response.delete_cookie("cf_refresh")
        return {"ok": True}

    @router.get("/me")
    def me(request: Request):
        user = _current_user(request)
        if not user:
            raise ApiError(401, "not_authenticated", "You are not logged in.")
        return _user_out(user)

    @router.post("/refresh")
    def refresh(response: Response, cf_refresh: str | None = Cookie(default=None)):
        if not cf_refresh:
            raise ApiError(401, "no_refresh_token", "No refresh token.")
        user_id = decode_refresh_token(cf_refresh)
        if not user_id:
            raise ApiError(401, "invalid_refresh_token", "Refresh token is invalid or expired.")
        user = user_store.get_by_id(user_id)
        if not user:
            raise ApiError(401, "user_not_found", "User no longer exists.")
        tokens = _set_tokens(response, user["id"], user["email"])
        return {"user": _user_out(user), **tokens}

    @router.get("/stats")
    def stats(request: Request):
        user = _current_user(request)
        if not user:
            raise ApiError(401, "not_authenticated", "You are not logged in.")
        return user_store.user_stats(user["id"])

    return router, _current_user

