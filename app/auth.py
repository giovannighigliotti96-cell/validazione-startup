from fastapi import Header, HTTPException

from app.config import get_settings


def require_cron(x_cron_token: str = Header(default="")) -> None:
    if x_cron_token != get_settings().cron_token:
        raise HTTPException(401, "invalid X-Cron-Token")


def require_api(x_api_token: str = Header(default="")) -> None:
    expected = get_settings().api_token
    if expected and x_api_token != expected:
        raise HTTPException(401, "invalid X-API-Token")
