import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import cron, keyword_sets, landing, opportunities, runs, signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Validazione Start-up — signal engine",
    version="0.1.0",
    description=(
        "Fase 1: raccolta e strutturazione segnali di domanda (Reddit, HN, store reviews, Trustpilot, IH), "
        "offerta (Product Hunt), trend (Google Trends), funnel di validazione con notifiche email. "
        "Il layer semantico (Claude API) è uno stub in app/services/analysis.py."
    ),
)

app.include_router(keyword_sets.router)
app.include_router(runs.router)
app.include_router(signals.router)
app.include_router(opportunities.router)
app.include_router(cron.router)
app.include_router(landing.router)
from app.routers import poltrona as _poltrona  # noqa: E402

app.include_router(_poltrona.router)
from app.routers import guida as _guida  # noqa: E402

app.include_router(_guida.router)
app.mount("/static", StaticFiles(directory="public"), name="static")  # page assets, ad images


@app.get("/", include_in_schema=False)
def root():
    from fastapi.responses import RedirectResponse

    from app.config import get_settings

    home = get_settings().landing_home_cluster
    if home:
        return RedirectResponse(f"/lp/{home}", status_code=302)
    return {"service": "validazione-startup", "docs": "/docs"}


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


from fastapi.responses import RedirectResponse as _Redirect  # noqa: E402


@app.api_route("/privacy", methods=["GET", "HEAD"], include_in_schema=False)
def _privacy_root():
    return _Redirect("/pl/privacy", status_code=308)
