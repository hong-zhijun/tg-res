from fastapi import HTTPException, Request

PUBLIC_PATHS = {"/login", "/static", "/favicon.ico"}


async def require_auth(request: Request) -> None:
    if any(request.url.path.startswith(path) for path in PUBLIC_PATHS):
        return
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=307, headers={"Location": "/login"})


def verify_password(submitted_password: str, expected_password: str) -> bool:
    return submitted_password == expected_password


async def require_api_auth(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")
