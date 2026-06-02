# ticket-support-system
Direct answer — do these edits to your existing files (no new files required). I’ll list exactly what to change, why, and give the exact code snippets you should paste into each file.

Summary of what to change
- Fix a bug and tighten time comparisons in app/modules/auth/service.py (refresh_session, get_user_from_access_token, change_password_using_access_token return).
- Ensure access + refresh cookies are set (and rotated) in all login/register/google flows in app/modules/auth/routes.py.
- Keep the automatic silent refresh behavior in app/dependencies.py (it already contains logic) — small improvements suggested.
- Make sure app/security.py properly creates/decodes tokens and returns timezone-safe expirations (I show a corrected version).
- Add a small POST refresh endpoint in routes.py (optional because dependencies already rotates tokens on request; still useful for client JS heartbeat).

1) Fixes and improvements for app/modules/auth/service.py
- Bug: refresh_session was checking a non-existent variable (access_token). Replace that check with refresh_token and use utc-naive comparisons consistently.
- Use datetime.utcnow() for comparisons with DB-stored naive UTC datetimes (safer and consistent).
- Ensure change_password_using_access_token returns the updated user at the end.

Replace or patch the functions below into service.py:

a) get_user_from_access_token — use datetime.utcnow() comparison
```python
from datetime import datetime, timezone

async def get_user_from_access_token(
    db: AsyncSession,
    access_token: str,
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is required")

    try:
        payload = decode_token(access_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Please login again",
        )

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    session = await auth_repo.get_session_by_access_token(db, access_token)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired, please login again")

    # session.access_expires_at is stored as a naive UTC datetime; compare with utcnow()
    if session.access_expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Access token expired, please login again")

    user = await auth_repo.get_user_by_id(db, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user
```

b) refresh_session — fix variable name, compare with datetime.utcnow(), rotate session correctly
```python
async def refresh_session(db: AsyncSession, refresh_token: str):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is required")

    old = await auth_repo.get_session_by_refresh_token(db, refresh_token)
    if not old:
        raise HTTPException(status_code=401, detail="Session expired, please login again")

    if old.refresh_expires_at < datetime.utcnow():
        # expired refresh token — delete old session
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

    # rotate session: remove old one
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
```

c) change_password_using_access_token — return user
```python
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
```

2) Ensure app/security.py is correct (token creation, decode)
- You already posted security.py. Use a version that:
  - Exposes create_access_token(user_id, org_context) -> (token, expiration naive UTC)
  - create_refresh_token(user_id) -> (token, expiration naive UTC)
  - decode_token raises ValueError for invalid / expired
- Example (paste into security.py if needed) — the content you already have is correct after the earlier corrections. Two important notes:
  - Return expirations as naive UTC datetimes (exp.replace(tzinfo=None)) so they compare cleanly with DB-naive datetimes.
  - build_token_payload should include org info for access tokens.

(You said you'll do changes yourself — you already have that file; just keep the corrected version.)

3) Modify app/modules/auth/routes.py — set refresh cookie & rotate on refresh
- In your login/register/google flows you set only access_token cookie. Also set refresh_token cookie there.
- Also add a POST /auth/refresh-token endpoint so client JS can proactively refresh.

Patch examples (replace the cookie-setting blocks in these functions):

a) In google_callback — after create_login_session returns session:
```python
res.set_cookie(
    key="access_token",
    value=session.access_token,
    httponly=True,
    path="/",
    samesite="lax",
)
res.set_cookie(
    key="refresh_token",
    value=session.refresh_token,
    httponly=True,
    path="/",
    samesite="lax",
)
```

b) In register_submit, same cookies:
```python
res.set_cookie(
    key="access_token",
    value=session.access_token,
    httponly=True,
    path="/",
    samesite="lax",
)
res.set_cookie(
    key="refresh_token",
    value=session.refresh_token,
    httponly=True,
    path="/",
    samesite="lax",
)
```

c) In login_submit, same cookies:
```python
res.set_cookie(
    key="access_token",
    value=session.access_token,
    httponly=True,
    path="/",
    samesite="lax",
)
res.set_cookie(
    key="refresh_token",
    value=session.refresh_token,
    httponly=True,
    path="/",
    samesite="lax",
)
```

d) Add a refresh endpoint (optional but convenient) at the bottom of routes.py:
```python
from fastapi.responses import JSONResponse
from fastapi import HTTPException

@auth_router.post("/auth/refresh-token")
async def refresh_token_endpoint(request: Request, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        session = await auth_service.refresh_session(db, refresh_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

    response = JSONResponse({"status": "ok"})
    response.set_cookie(key="access_token", value=session.access_token, httponly=True, path="/", samesite="lax")
    response.set_cookie(key="refresh_token", value=session.refresh_token, httponly=True, path="/", samesite="lax")
    return response
```

4) app/dependencies.py — your get_current_user already attempts silent refresh
- You already implemented the behavior: when get_user_from_access_token fails, it reads refresh_token cookie, calls refresh_session and then sets cookies on the Response return.
- Suggested improvements (not required but recommended):
  - Use datetime.utcnow() in service checks (done above).
  - When you set cookies on response, set SameSite and Secure if running on HTTPS:
    response.set_cookie(key="access_token", value=session.access_token, httponly=True, secure=True, samesite="lax", path="/")
    response.set_cookie(key="refresh_token", value=session.refresh_token, httponly=True, secure=True, samesite="lax", path="/")

Your get_current_user currently:
```python
async def get_current_user(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    access = request.cookies.get("access_token")
    if not access:
        return None

    try:
        user = await get_user_from_access_token(db, access)
        return user.id
    except HTTPException:
        pass

    refresh = request.cookies.get("refresh_token")
    if not refresh:
        return None
    try:
        session = await refresh_session(db, refresh)
    except Exception:
        return None
    try:
        user = await get_user_from_access_token(db, session.access_token)
    except Exception:
        return None
    response.set_cookie(key="access_token", value=session.access_token, httponly=True, path="/")
    response.set_cookie(key="refresh_token", value=session.refresh_token, httponly=True, path="/")
    return user.id
```
- This is fine; just consider adding secure=True in production and samesite and an expiry value (expires or max_age).

5) Important notes and deployment checklist
- DB session token fields: Your models store access_expires_at and refresh_expires_at as DateTime (naive). Ensure you store the expiration datetimes as naive UTC when creating sessions (the security.create_* functions use .replace(tzinfo=None) — good).
- Cookie security:
  - In production set secure=True (only send over HTTPS).
  - httponly=True (already set) to prevent JS reads.
  - samesite="lax" or "strict" by policy.
  - If you want JS to proactively call /auth/refresh-token, do NOT set HttpOnly on refresh cookie; but that is less secure. Better approach: keep both cookies httponly and rely on middleware/deps to refresh on next request or send POST refresh request and let browser include cookies (credentials: include). Browser will still send HttpOnly cookies with fetch when credentials: 'include' is set.
- Client-side proactive refresh:
  - If you want the browser to proactively refresh (so no user-visible 401 occurs even when idle), add a small JS heartbeat calling POST /auth/refresh-token every N minutes (e.g., every 13 minutes). Use fetch with credentials: 'include'.
- Logout behavior:
  - logout() already deletes session by access token and you already delete cookies in routes.logout. Ensure you also remove session rows associated with user when user logs out from all devices (you already have delete_all_user_sessions).

6) Minimal optional JavaScript to proactively refresh (paste into base template)
```html
<script>
async function refreshTokenHeartbeat() {
  try {
    const res = await fetch('/auth/refresh-token', {
      method: 'POST',
      credentials: 'include',
    });
    if (!res.ok) {
      // refresh failed — redirect to login
      window.location.href = '/auth/login?error=Session+expired';
    }
  } catch (err) {
    console.error('Heart refresh failed', err);
  }
}
// every 13 minutes
setInterval(refreshTokenHeartbeat, 13 * 60 * 1000);
</script>
```
Note: because cookies are httpOnly, fetch will still include them if credentials: 'include' is set. No need to expose refresh token to JS.

7) Tests to run locally after changes
- Register via web flow: verify both access_token and refresh_token cookies are set.
- Wait > ACCESS_TOKEN_MINUTES, perform an authenticated page load → should still work because get_current_user will rotate token and set new cookies.
- Call POST /auth/refresh-token with cookies included and verify cookies are rotated.
- Logout and verify session removed from DB and cookies deleted.
- Change password and ensure all sessions invalidated (users logged out).

Implementation plan (in order)
1. Update service.py functions (get_user_from_access_token, refresh_session, change_password_using_access_token).
2. Update routes.py to set both cookies in login/register/google_callback and add the refresh endpoint.
3. (Optional) Update templates to include JS heartbeat.
4. Run local tests described above.
5. Add secure=True to cookies in production.

If you want, I can produce exact file diffs/patches for each file (copy-paste ready). Which files would you like the full patch for now (service.py, routes.py, dependencies.py, security.py)?
