"""Trigger a Cloud Run Job execution (scripts/job.py <name> <args>) from the web app. The web service runs with CPU
throttled (billed per request), so anything slower than a request goes through here. Falls back to a local thread
when not on Cloud Run (local dev)."""
from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger("jobs")
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or "validation-start-up"
REGION = os.environ.get("JOBS_REGION") or "europe-west1"
JOB = os.environ.get("JOBS_NAME") or "validazione-jobs"


def on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE"))


def trigger(name: str, *args: str) -> bool:
    """Start `python -m scripts.job name args...` as a job execution. Returns True if the job was started."""
    if not on_cloud_run():
        return _local(name, *args)
    try:
        import google.auth
        import google.auth.transport.requests
        import httpx

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(google.auth.transport.requests.Request())
        url = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs/{JOB}:run"
        body = {"overrides": {"containerOverrides": [{"args": ["python", "-m", "scripts.job", name, *args]}]}}
        r = httpx.post(url, json=body, headers={"Authorization": f"Bearer {creds.token}"}, timeout=15)
        if r.status_code >= 300:
            log.error("job %s trigger failed: %s %s", name, r.status_code, r.text[:200])
            return _local(name, *args)
        log.info("job %s started: %s", name, (r.json().get("metadata") or {}).get("name", "")[-40:])
        return True
    except Exception as e:  # noqa: BLE001
        log.error("job %s trigger error: %s", name, e)
        return _local(name, *args)


def _local(name: str, *args: str) -> bool:
    from scripts import job as _job

    threading.Thread(target=lambda: _job.JOBS[name](*args), daemon=True).start()
    return True
