"""Meta Conversions API: server-side events that mirror the browser pixel (same event_id => Meta deduplicates).
Server events carry hashed email/phone/name plus IP, user agent and the _fbp/_fbc cookies, so matching (and the
optimisation of a Sales campaign) does not depend on the browser, ad blockers or iOS."""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid

from app.config import get_settings

log = logging.getLogger("capi")
API = "https://graph.facebook.com/v21.0"


def new_event_id() -> str:
    return uuid.uuid4().hex


def _h(v: str | None) -> list[str]:
    v = (v or "").strip().lower()
    return [hashlib.sha256(v.encode()).hexdigest()] if v else []


def _phone(v: str | None) -> list[str]:
    d = re.sub(r"\D", "", v or "")
    if not d:
        return []
    if d.startswith("00"):
        d = d[2:]
    elif not d.startswith("39"):
        d = "39" + d.lstrip("0")
    return [hashlib.sha256(d.encode()).hexdigest()]


def user_data(request=None, email: str | None = None, phone: str | None = None, first_name: str | None = None, last_name: str | None = None, external_id: str | None = None) -> dict:
    ud: dict = {}
    if request is not None:
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "")
        try:
            import ipaddress

            if ip and ipaddress.ip_address(ip).is_global:
                ud["client_ip_address"] = ip
        except ValueError:
            pass
        ua = request.headers.get("user-agent")
        if ua:
            ud["client_user_agent"] = ua[:300]
        for ck in ("_fbp", "_fbc"):
            if request.cookies.get(ck):
                ud[ck.lstrip("_")] = request.cookies[ck]
        if not ud.get("fbc"):
            fbclid = request.query_params.get("fbclid") if hasattr(request, "query_params") else None
            if fbclid:
                ud["fbc"] = f"fb.1.{int(time.time() * 1000)}.{fbclid}"
    if email:
        ud["em"] = _h(email)
    if phone:
        ud["ph"] = _phone(phone)
    if first_name:
        ud["fn"] = _h(first_name)
    if last_name:
        ud["ln"] = _h(last_name)
    if external_id:
        ud["external_id"] = _h(external_id)
    ud.setdefault("country", _h("it"))
    return ud


def send(event_name: str, event_id: str, source_url: str, ud: dict, custom: dict | None = None, test_code: str | None = None) -> None:
    """Fire-and-forget (thread): never slows a request, never raises."""
    s = get_settings()
    pixel = getattr(s, "meta_pixel_id", "") or ""
    token = getattr(s, "meta_capi_token", "") or getattr(s, "meta_access_token", "") or ""
    if not pixel or not token:
        return
    if not (ud.get("em") or ud.get("ph") or (ud.get("client_ip_address") and ud.get("client_user_agent"))):
        return  # Meta rejects events without usable match keys (e.g. local tests)
    payload = {"event_name": event_name, "event_time": int(time.time()), "event_id": event_id, "action_source": "website",
               "event_source_url": source_url, "user_data": ud}
    if custom:
        payload["custom_data"] = custom

    import json

    import httpx

    try:
        data = {"access_token": token, "data": json.dumps([payload])}
        if test_code:
            data["test_event_code"] = test_code
        r = httpx.post(f"{API}/{pixel}/events", data=data, timeout=2.5)
        j = r.json()
        if not j.get("events_received"):
            log.warning("capi %s: %s", event_name, j)
    except Exception as e:  # noqa: BLE001
        log.warning("capi %s failed: %s", event_name, e)
