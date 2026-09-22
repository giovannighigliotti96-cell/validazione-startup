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

    return RedirectResponse("/pl", status_code=302)  # the two-door home


@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


from fastapi.responses import RedirectResponse as _Redirect  # noqa: E402


@app.api_route("/privacy", methods=["GET", "HEAD"], include_in_schema=False)
def _privacy_root():
    return _Redirect("/pl/privacy", status_code=308)


from fastapi.responses import PlainTextResponse as _Plain, Response as _Resp  # noqa: E402


@app.get("/robots.txt", include_in_schema=False)
def _robots():
    base = "https://poltronalibera.it"
    return _Plain(f"User-agent: *\nAllow: /lp/\nAllow: /pl/\nDisallow: /pl/admin\nDisallow: /pl/annuncio/\nDisallow: /pl/guida/download/\nDisallow: /cron/\nSitemap: {base}/sitemap.xml\n")


@app.get("/sitemap.xml", include_in_schema=False)
def _sitemap():
    base = "https://poltronalibera.it"
    urls = ["/pl", "/lp/poltrona_libera_titolari", "/lp/poltrona_libera_professioniste", "/pl/postazioni", "/pl/guida/squadra", "/pl/guida/poltrona", "/pl/privacy"]
    body = "".join(f"<url><loc>{base}{u}</loc><changefreq>daily</changefreq></url>" for u in urls)
    return _Resp(content=f"<?xml version='1.0' encoding='UTF-8'?><urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>{body}</urlset>", media_type="application/xml")
