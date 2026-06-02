Yes — it's feasible to avoid storing any separate session identifier in the client by using the access_token cookie itself as the pointer to the DB session row. In that approach the server:

- keeps the refresh_token only in DB (never in cookies),
- stores only access_token (JWT) in an HttpOnly cookie (as you already do),
- when access token is expired (or invalid), the server looks up the session row by matching the raw access_token string (from the cookie) to SessionToken.access_token in DB, checks refresh_expires_at, and rotates the session (delete old row → create new access/refresh pair) and sets the new access_token cookie.

That approach is simple to implement and avoids adding any new client-side cookie. Below I give the exact, minimal changes you should paste into your existing files to implement it, then explain the security trade-offs and the resulting flow.

What to change (copy/paste ready)
- app/modules/auth/service.py — add refresh_session_by_access_token, fix get_user_from_access_token and change_password_using_access_token return
- app/dependencies.py — update get_current_user to attempt server-side refresh by access_token cookie when JWT validation fails
- app/modules/auth/routes.py — make login/register/google set only access_token cookie (no refresh cookie), keep or add a POST /auth/refresh-token endpoint that triggers the same rotation using access_token cookie (optional; useful for client heartbeat)

1) app/modules/auth/service.py
Replace/patch the functions below into your service.py (keep other imports and functions). This assumes auth_repo has get_session_by_access_token, get_session_by_refresh_token, save_session, delete_session_by_id, etc. (as in your repo).

```python
# app/modules/auth/service.py
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth import repository as auth_repo
from app.modules.auth.models import Users, SessionToken
from app.modules.auth.schemas import Register, Login, ChangePassword, GoogleUserInfo
from app.security import (
    validate_password,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

# ---------- validate access token and check DB session ----------
async def get_user_from_access_token(
    db: AsyncSession,
    access_token: str,
):
    """
    Validate access token and DB session. Raises HTTPException on failure.
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is required")

    try:
        payload = decode_token(access_token)
    except Exception:
        # token decode failed (invalid or expired)
        raise HTTPException(status_code=401, detail="Please login again")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    # ensure DB session exists and hasn't been removed
    session = await auth_repo.get_session_by_access_token(db, access_token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired, please login again")

    # DB datetimes are naive UTC — compare with datetime.utcnow()
    if session.access_expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Access token expired, please login again")

    user = await auth_repo.get_user_by_id(db, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


# ---------- rotate session using a refresh token string (kept) ----------
async def refresh_session(db: AsyncSession, refresh_token: str):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    old = await auth_repo.get_session_by_refresh_token(db, refresh_token)
    if not old:
        raise HTTPException(status_code=401, detail="Session expired, please login again")

    if old.refresh_expires_at < datetime.utcnow():
        await auth_repo.delete_session_by_id(db, old.id)
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = await auth_repo.get_user_by_id(db, old.user_id)
    if not user:
        await auth_repo.delete_session_by_id(db, old.id)
        await db.commit()
        raise HTTPException(status_code=401, detail="User not found")

    org_context = None
    if user.auth_provider == "local":
        org_context = await auth_repo.get_primary_org_context(db, user.id)

    # rotate: delete old and create new session
    await auth_repo.delete_session_by_id(db, old.id)

    access_token, access_exp = create_access_token(user.id, org_context)
    new_refresh, refresh_exp = create_refresh_token(user.id)

    new_session = SessionToken(
        user_id=user.id,
        access_token=access_token,
        refresh_token=new_refresh,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )

    await auth_repo.save_session(db, new_session)
    await db.commit()
    await db.refresh(new_session)

    return new_session


# ---------- rotate session by matching the raw access_token string ----------
async def refresh_session_by_access_token(db: AsyncSession, access_token: str):
    """
    Use the raw access_token cookie value to locate the DB session, validate
    its refresh_expires_at, and rotate the session. Returns the new session row.
    This keeps refresh_token only in DB and does not expose it to the client.
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is required")

    # find the DB session by access token string
    old = await auth_repo.get_session_by_access_token(db, access_token)
    if not old:
        raise HTTPException(status_code=401, detail="Session not found")

    # check refresh expiry in DB
    if old.refresh_expires_at < datetime.utcnow():
        await auth_repo.delete_session_by_id(db, old.id)
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = await auth_repo.get_user_by_id(db, old.user_id)
    if not user:
        await auth_repo.delete_session_by_id(db, old.id)
        await db.commit()
        raise HTTPException(status_code=401, detail="User not found")

    org_context = None
    if user.auth_provider == "local":
        org_context = await auth_repo.get_primary_org_context(db, user.id)

    # rotate: remove old session row and create a new one
    await auth_repo.delete_session_by_id(db, old.id)

    access_token_new, access_exp = create_access_token(user.id, org_context)
    new_refresh, refresh_exp = create_refresh_token(user.id)

    new_session = SessionToken(
        user_id=user.id,
        access_token=access_token_new,
        refresh_token=new_refresh,
        access_expires_at=access_exp,
        refresh_expires_at=refresh_exp,
    )

    await auth_repo.save_session(db, new_session)
    await db.commit()
    await db.refresh(new_session)

    return new_session


# ---------- change password (return user) ----------
async def change_password_using_access_token(
    db: AsyncSession,
    access_token: str,
    data: ChangePassword,
):
    user = await get_user_from_access_token(db, access_token)

    if user.auth_provider == "google":
        raise HTTPException(status_code=400, detail="Google account user can't change password!")

    if not verify_password(data.current_password, user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if data.new_password != data.confirm_new_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    try:
        validate_password(data.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user.password = hash_password(data.new_password)
    db.add(user)

    # invalidate existing sessions
    await auth_repo.delete_all_user_sessions(db, user.id)

    await db.commit()
    await db.refresh(user)

    return user


# ---------- logout helper ----------
async def logout(
    db: AsyncSession,
    access_token: str | None = None,
    session_id: int | None = None,
):
    if session_id:
        await auth_repo.delete_session_by_id(db, session_id)
        await db.commit()
        return

    if access_token:
        await auth_repo.delete_session_by_access_token(db, access_token)
        await db.commit()
```

2) app/dependencies.py
Replace your existing get_current_user with this (it uses only the access_token cookie; when the token is invalid/expired it calls refresh_session_by_access_token to rotate using the DB-stored refresh token):

```python
# app/dependencies.py
from fastapi import Header, HTTPException, status, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db.parent_db import get_db
from app.core.db.tenant_db import get_tenant_db_session
from app.modules.organizations.models import Organizations, OrganizationMembers
from app.modules.auth.service import get_user_from_access_token, refresh_session_by_access_token

async def get_current_user(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """
    Return current user id or None.
    If access token is expired/invalid, attempt to refresh using the raw access_token cookie
    by matching it against the DB session row (which stores the refresh token).
    """
    access = request.cookies.get("access_token")
    if not access:
        return None

    # Try to validate access token normally (decoding + DB check)
    try:
        user = await get_user_from_access_token(db, access)
        return user.id
    except HTTPException:
        # decode failed or access expired; try server-side refresh using the raw access token string
        pass

    # Attempt to refresh the session by looking up the session row using the raw access token
    try:
        new_session = await refresh_session_by_access_token(db, access)
    except Exception:
        return None

    # Validate the newly created access token and fetch user
    try:
        user = await get_user_from_access_token(db, new_session.access_token)
    except Exception:
        return None

    # Set the rotated access token cookie (we never expose refresh_token to client)
    response.set_cookie(
        key="access_token",
        value=new_session.access_token,
        httponly=True,
        path="/",
        samesite="lax",
        # secure=True  # enable in production
    )

    return user.id
```

3) app/modules/auth/routes.py
Set only the access_token cookie at login/register/google (do not set refresh_token cookie). Also add (optional) POST /auth/refresh-token endpoint that rotates using access_token cookie (this is useful if your client wants to proactively keep the session alive).

- Replace cookie-setting blocks after successful login/register/google with:

```python
res.set_cookie(
    key="access_token",
    value=session.access_token,
    httponly=True,
    path="/",
    samesite="lax",
    # secure=True  # enable in production
)
# DO NOT set refresh_token cookie or session_id cookie
```

- Add a refresh endpoint (optional):

```python
from fastapi.responses import JSONResponse
from fastapi import HTTPException

@auth_router.post("/auth/refresh-token")
async def refresh_token_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Proactively rotate session using the raw access_token cookie (server-side refresh token in DB).
    Client should call this with credentials included; the server will rotate and set a new access cookie.
    """
    access_cookie = request.cookies.get("access_token")
    if not access_cookie:
        raise HTTPException(status_code=401, detail="Access token not found")

    try:
        new_session = await auth_service.refresh_session_by_access_token(db, access_cookie)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    resp = JSONResponse({"status": "ok"})
    resp.set_cookie(key="access_token", value=new_session.access_token, httponly=True, path="/", samesite="lax")
    return resp
```

Also update logout to delete the DB session row by access_token cookie when present:

```python
@auth_router.post("/auth/logout")
async def logout_submit(request: Request, db: AsyncSession = Depends(get_db)):
    access = request.cookies.get("access_token")
    try:
        if access:
            await auth_service.logout(db, access_token=access)
    except Exception:
        pass

    res = RedirectResponse(url="/auth/login?msg=Logged out successfully", status_code=303)
    res.delete_cookie("access_token", path="/")
    return res
```

(If you still keep other logout behaviors, keep them consistent — ensure DB session row is deleted.)

Flow after these changes
- Login/register/google:
  - Server creates a SessionToken DB row with access_token (JWT), refresh_token (secret), expiry timestamps; returns access_token in HttpOnly cookie only (no refresh cookie).
- On each request:
  - get_current_user tries to decode and validate access token and checks DB row exists and not expired → if OK, request proceeds.
  - If decode fails or access expired, get_current_user calls refresh_session_by_access_token(db, raw_access_cookie):
    - server finds the DB session by matching the raw access_token string,
    - verifies refresh_expires_at,
    - deletes old row and creates new session row (new access_token + new refresh_token),
    - returns new_session to caller,
    - get_current_user sets a new access_token cookie and returns the user.
- Logout:
  - server deletes DB session row (by access_token) and removes access cookie.

Security trade-offs and mitigations (short summary)
- Similar to any cookie-based approach: whoever obtains the access_token cookie can both access resources (until access_expires_at) and, if access token still present, can trigger refresh to get a new access token (until refresh_expires_at) — because the raw cookie is used to find the session row in DB for rotation.
- Pros of this approach:
  - No extra session identifier cookie; implementation is minimal.
  - Refresh token itself never leaves DB.
  - Simpler client: only one cookie to manage (access_token).
- Cons / risks:
  - If an attacker steals the access_token cookie (via XSS or other means), they can use it to refresh and get a new access token. That risk exists for any cookie or token the client holds.
  - If the DB is compromised with write access, the attacker can tamper with session rows — unavoidable with DB compromise.
- Mitigations (recommended):
  - Keep cookies HttpOnly and Secure (HTTPS) and SameSite to reduce XSS/CSRF exposure.
  - Rotate sessions on refresh (we already delete old row and create new one).
  - Short access_token lifetime (15 minutes) and reasonable refresh lifetime (e.g., 30 days).
  - Optionally record metadata in the SessionToken row (user_agent, IP) and validate on refresh to reduce risk of stolen cookie reuse from other devices/locations.
  - Rate-limit refresh endpoints and audit refresh events.
  - On critical actions (password change, email change), delete_all_user_sessions to force re-login.

Is this the best option?
- It's a good, pragmatic option if you want to avoid any additional cookie and keep refresh_token server-only. It is simpler than the "session_key hash" approach and reduces the number of moving parts.
- If you want a stronger containment of refresh capability in case a cookie is stolen, the session_key-hash approach (store a random token in cookie and only the hash in DB) is slightly stronger against DB leaks (DB only contains hashes). But both approaches still expose a client-side secret (access_token cookie vs session_key cookie) that can be stolen by XSS.
- If you want maximum protection from stolen cookies, you need more advanced measures: short refresh lifetimes, device binding, re-auth for sensitive operations, refresh proofs (PKCE-like), or storing refresh tokens in a secure client storage using secure channels (not feasible for server-rendered web apps).

Concluding recommendation
- If you prefer minimal change and to avoid storing any session ID cookie: implement the changes above (refresh by access_token DB lookup). It will meet your requirement: refresh_token only in DB and access token gets rotated/kept alive transparently.
- Additionally implement these hardening steps:
  - set cookies with secure=True in production,
  - add user_agent and optionally IP checks in SessionToken,
  - log/monitor refresh calls and failed refresh attempts,
  - invalidate all sessions on password change.

If you want, I can now produce:
- a) exact full-file patches (copy-paste ready) for service.py, dependencies.py and routes.py implementing the refresh-by-access-token approach; OR
- b) the alternative stronger session_key_hash implementation that stores a hashed random session key in DB and plaintext in cookie (more protection in DB leak scenarios).

Which do you want me to generate now — (a) minimal access_token-based patches or (b) session_key_hash-based patches?
