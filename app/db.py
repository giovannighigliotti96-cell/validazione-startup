"""
Firestore data layer.

Collections (see firestore/SCHEMA.md for field-level docs):
  keyword_sets/{id}
  scrape_runs/{id}
  raw_signals/{source}__{external_id}        <- doc id IS the dedup key
  trend_snapshots/{keyword}__{geo}__{timeframe}__{YYYY-MM-DD}
  problem_clusters/{id}
  problem_clusters/{id}/signals/{signal_id}   <- cluster <-> signal join
  competitor_signals/{source}__{external_id}
  opportunity_scoring/{cluster_id}            <- funnel state + embedded market_estimates
  funnel_stages/{key}
  validation_experiments/{id}
  notifications/{id}
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Iterable

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Client, DocumentReference

from app.config import get_settings

# Collection names as constants so a rename is a one-line change
KEYWORD_SETS = "keyword_sets"
SCRAPE_RUNS = "scrape_runs"
RAW_SIGNALS = "raw_signals"
TREND_SNAPSHOTS = "trend_snapshots"
PROBLEM_CLUSTERS = "problem_clusters"
CLUSTER_SIGNALS_SUB = "signals"
COMPETITOR_SIGNALS = "competitor_signals"
OPPORTUNITY_SCORING = "opportunity_scoring"
FUNNEL_STAGES = "funnel_stages"
VALIDATION_EXPERIMENTS = "validation_experiments"
NOTIFICATIONS = "notifications"

FIRESTORE_BATCH_LIMIT = 400  # hard limit is 500 writes per batch


@lru_cache
def get_db() -> Client:
    s = get_settings()
    if not firebase_admin._apps:
        if s.firebase_service_account_b64:
            info = json.loads(base64.b64decode(s.firebase_service_account_b64))
            cred = credentials.Certificate(info)
        elif s.google_application_credentials and os.path.exists(s.google_application_credentials):
            cred = credentials.Certificate(s.google_application_credentials)
        else:
            # Cloud Run / GCE: Application Default Credentials
            cred = credentials.ApplicationDefault()
        opts = {"projectId": s.firebase_project_id} if s.firebase_project_id else None
        firebase_admin.initialize_app(cred, opts)
    return firestore.client()


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


_BAD_ID = re.compile(r"[/\s]+")


def safe_id(*parts: str) -> str:
    """Firestore doc ids cannot contain '/', must be <= 1500 bytes."""
    joined = "__".join(_BAD_ID.sub("_", str(p)) for p in parts if p is not None)
    if len(joined.encode()) > 1400:
        joined = hashlib.sha256(joined.encode()).hexdigest()
    return joined


def signal_doc_id(source: str, external_id: str) -> str:
    return safe_id(source, external_id)


def hash_author(source: str, username: str | None) -> str | None:
    """GDPR: we never store usernames, only a salted hash (enough to count distinct authors)."""
    if not username:
        return None
    salt = get_settings().author_hash_salt
    return hashlib.sha256(f"{salt}:{source}:{username}".encode()).hexdigest()[:32]


def doc_to_dict(snap) -> dict | None:
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d["id"] = snap.id
    return d


def chunks(items: list, n: int) -> Iterable[list]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


# ---------------------------------------------------------------------------
# generic CRUD
# ---------------------------------------------------------------------------
def get(collection: str, doc_id: str) -> dict | None:
    return doc_to_dict(get_db().collection(collection).document(doc_id).get())


def list_all(collection: str, limit: int = 1000, **where: Any) -> list[dict]:
    q = get_db().collection(collection)
    for field, value in where.items():
        q = q.where(field, "==", value)
    return [doc_to_dict(s) for s in q.limit(limit).stream()]


def upsert(collection: str, doc_id: str | None, data: dict, merge: bool = True) -> str:
    doc_id = doc_id or new_id()
    data = {**data, "updated_at": now()}
    get_db().collection(collection).document(doc_id).set(data, merge=merge)
    return doc_id


def delete(collection: str, doc_id: str) -> None:
    get_db().collection(collection).document(doc_id).delete()


def insert_new_only(collection: str, docs: dict[str, dict]) -> tuple[int, int]:
    """
    Insert docs keyed by doc id, skipping ids that already exist.
    Returns (inserted, skipped). Used by scrapers for dedup on natural keys.
    """
    if not docs:
        return 0, 0
    db = get_db()
    col = db.collection(collection)
    ids = list(docs.keys())
    existing: set[str] = set()
    for chunk in chunks(ids, 300):
        refs = [col.document(i) for i in chunk]
        for snap in db.get_all(refs):
            if snap.exists:
                existing.add(snap.id)
    to_insert = [i for i in ids if i not in existing]
    ts = now()
    for chunk in chunks(to_insert, FIRESTORE_BATCH_LIMIT):
        batch = db.batch()
        for i in chunk:
            batch.set(col.document(i), {**docs[i], "created_at": ts, "updated_at": ts})
        batch.commit()
    return len(to_insert), len(existing)


def count(collection: str, **where: Any) -> int:
    q = get_db().collection(collection)
    for field, value in where.items():
        q = q.where(field, "==", value)
    res = q.count().get()
    return int(res[0][0].value)
