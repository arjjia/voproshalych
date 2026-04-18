"""Basic auth для admin API."""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from admin.config import settings


security = HTTPBasic(auto_error=False)


def require_admin_auth(
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={"WWW-Authenticate": "Basic"},
    )
    if credentials is None:
        raise unauthorized

    is_valid_username = secrets.compare_digest(
        credentials.username, settings.admin_auth_username
    )
    is_valid_password = secrets.compare_digest(
        credentials.password, settings.admin_auth_password
    )
    if not (is_valid_username and is_valid_password):
        raise unauthorized
