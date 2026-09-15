"""HTML email notifications (SMTP via Gmail app password, or Resend). Logged to `notifications`."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import httpx

from app import db
from app.config import get_settings

log = logging.getLogger("notify")


def _fmt_eur(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    if v >= 1e9:
        return f"€{v/1e9:.1f}B"
    if v >= 1e6:
        return f"€{v/1e6:.1f}M"
    if v >= 1e3:
        return f"€{v/1e3:.0f}k"
    return f"€{v:.0f}"


def _badge(sat: str | None) -> str:
    colors = {"blue": "#1d4ed8", "purple": "#7e22ce", "red": "#b91c1c"}
    c = colors.get(sat or "", "#6b7280")
    return f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;background:{c};color:#fff;font-size:12px;font-weight:600">{escape((sat or "n/a").upper())}</span>'


def render_stage_email(cluster: dict, opp: dict, stage: dict, evidence: dict | None = None) -> tuple[str, str]:
    """Returns (subject, html)."""
    s = get_settings()
    is_presale = stage["key"] == "presale_validation"
    title = "💳 VERIFICA CHE PAGHINO — " if is_presale else "📈 Funnel: "
    subject = f"{title}{cluster.get('name')} → {stage.get('name')}"
    base = s.public_base_url.rstrip("/")

    history_rows = "".join(
        f"<tr><td style='padding:4px 8px;color:#6b7280'>{escape(str(h.get('at',''))[:16])}</td>"
        f"<td style='padding:4px 8px'>{escape(h.get('stage',''))}</td>"
        f"<td style='padding:4px 8px;color:#374151'>{escape(h.get('reason','') or '')}</td></tr>"
        for h in (opp.get("stage_history") or [])[-8:]
    )
    questions = "".join(f"<li>{escape(q)}</li>" for q in (cluster.get("mom_test_questions") or [])[:8])
    from app.services.explain import explain as _explain
    ev_rows = "".join(
        f"<tr><td style='padding:4px 8px;color:#15803d'>✔</td><td style='padding:4px 8px'>{escape(_explain(k, None, {}).get('label') or k)} <span style='color:#6b7280'>({escape(str(v).lstrip('✔✘ '))})</span></td></tr>"
        for k, v in (evidence or {}).items()
    )

    presale_block = ""
    if is_presale:
        presale_block = f"""
        <div style="margin:20px 0;padding:16px;border:2px solid #b45309;border-radius:10px;background:#fffbeb">
          <h2 style="margin:0 0 8px;font-size:16px;color:#92400e">Prossimo passo: far tirare fuori la carta di credito</h2>
          <ol style="margin:0;padding-left:20px;color:#374151;font-size:14px;line-height:1.6">
            <li>Landing page con <b>prezzo visibile</b> e payment link (Stripe / Lemon Squeezy) — anche "pre-order, 50% off".</li>
            <li>Smoke test: €100-200 di Google Ads sulle keyword del problema, misura CTR e conversion → checkout.</li>
            <li>Ricontatta gli intervistati che hanno detto "lo comprerei": chiedi il pagamento oggi, non "quando esce".</li>
            <li>Registra l'esperimento: <code>POST {escape(base)}/experiments</code> con type=<b>presale</b> e metriche
                <code>{{"visitors","checkout_started","paid","revenue_eur"}}</code>. Il funnel passa a <b>validated</b> da solo.</li>
          </ol>
        </div>"""

    html = f"""
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:640px;margin:0 auto;padding:24px;color:#111827">
  <p style="margin:0 0 4px;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Validazione start-up · funnel</p>
  <h1 style="margin:0 0 6px;font-size:22px">{escape(cluster.get('name') or '')}</h1>
  <p style="margin:0 0 16px;color:#374151;font-size:15px">{escape(cluster.get('problem_statement') or '(problem statement non ancora compilato)')}</p>

  <p style="margin:0 0 16px;font-size:14px"><b>Nuova fase:</b> {escape(stage.get('name') or '')} &nbsp;·&nbsp; {escape(stage.get('description') or '')}</p>

  <table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:16px">
    <tr><td style="padding:6px 8px;color:#6b7280;width:45%">Verticale / persona</td><td style="padding:6px 8px">{escape(cluster.get('vertical') or '—')} / {escape(cluster.get('persona') or '—')}</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">Segnali (fonti · autori)</td><td style="padding:6px 8px">{cluster.get('signal_count') or 0} ({cluster.get('distinct_sources') or 0} · {cluster.get('distinct_authors') or 0})</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">TAM / SAM / SOM</td><td style="padding:6px 8px">{_fmt_eur(opp.get('tam_eur'))} / {_fmt_eur(opp.get('sam_eur'))} / {_fmt_eur(opp.get('som_eur'))} <span style="color:#6b7280">(conf. {escape(opp.get('market_confidence') or '—')})</span></td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">Saturazione · competitor</td><td style="padding:6px 8px">{_badge(opp.get('saturation'))} &nbsp; {opp.get('competitor_count') if opp.get('competitor_count') is not None else '—'} trovati</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">Founder fit · canale</td><td style="padding:6px 8px">{opp.get('founder_fit') or '—'}/5 · {escape(opp.get('acquisition_channel') or '—')}</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">Why now</td><td style="padding:6px 8px">{escape(opp.get('why_now') or '—')}</td></tr>
    <tr><td style="padding:6px 8px;color:#6b7280">Score complessivo</td><td style="padding:6px 8px"><b>{opp.get('overall_score') if opp.get('overall_score') is not None else '—'}</b>/100</td></tr>
  </table>

  {presale_block}
  {("<h3 style='font-size:14px;margin:16px 0 6px'>Precedenti reali (come sono partiti)</h3><ul style='font-size:13px;color:#374151'>" + "".join(f"<li><b>{escape(a.get('name',''))}</b>" + (" (bootstrapped)" if a.get('bootstrapped') else "") + f": {escape(a.get('how_they_found_the_problem') or '')} — primi clienti: {escape(a.get('first_customers_channel') or '')} — {escape(a.get('outcome') or '')} <a href='{escape(a.get('url') or '')}' style='color:#1d4ed8'>sito</a></li>" for a in (opp.get('analogues') or [])[:3]) + "</ul>") if opp.get('analogues') else ""}

  {"<h3 style='font-size:14px;margin:16px 0 6px'>Evidenza che ha fatto scattare la fase</h3><table style='font-size:13px;border-collapse:collapse'>" + ev_rows + "</table>" if ev_rows else ""}
  {"<h3 style='font-size:14px;margin:16px 0 6px'>Domande Mom Test</h3><ul style='font-size:13px;color:#374151'>" + questions + "</ul>" if questions else ""}
  {"<h3 style='font-size:14px;margin:16px 0 6px'>Storico fasi</h3><table style='font-size:13px;border-collapse:collapse'>" + history_rows + "</table>" if history_rows else ""}

  <p style="margin:20px 0 0;font-size:13px">
    <a href="{escape(base)}/opportunities/{escape(cluster.get('id') or '')}" style="color:#1d4ed8">Apri opportunità (JSON)</a> ·
    <a href="{escape(base)}/export/signals.csv?cluster_id={escape(cluster.get('id') or '')}" style="color:#1d4ed8">Esporta segnali CSV</a>
  </p>
  <p style="margin:16px 0 0;font-size:11px;color:#9ca3af">Inviata automaticamente dal motore funnel. Soglie in funnel_stages.</p>
</div>"""
    return subject, html


def send_email(subject: str, html: str) -> tuple[str, str | None]:
    """Returns (status, error)."""
    s = get_settings()
    to = s.notify_email_to
    if s.email_provider == "none" or not to:
        return "skipped", "EMAIL_PROVIDER=none or NOTIFY_EMAIL_TO empty"
    try:
        if s.email_provider == "resend":
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {s.resend_api_key}"},
                json={"from": s.notify_email_from or "onboarding@resend.dev", "to": [to], "subject": subject, "html": html},
                timeout=20,
            )
            r.raise_for_status()
        else:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = s.notify_email_from or s.smtp_user
            msg["To"] = to
            msg.attach(MIMEText("Apri il client in HTML per vedere il contenuto.", "plain"))
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as srv:
                srv.starttls()
                srv.login(s.smtp_user, s.smtp_password)
                srv.sendmail(msg["From"], [to], msg.as_string())
        return "sent", None
    except Exception as e:  # noqa: BLE001
        log.error("email failed: %s", e)
        return "failed", f"{type(e).__name__}: {e}"


def notify_stage(cluster: dict, opp: dict, stage: dict, evidence: dict | None = None) -> str:
    subject, html = render_stage_email(cluster, opp, stage, evidence)
    status, err = send_email(subject, html)
    db.upsert(
        db.NOTIFICATIONS,
        None,
        {"cluster_id": cluster["id"], "stage_key": stage["key"], "channel": "email",
         "recipient": get_settings().notify_email_to, "subject": subject, "status": status, "error": err, "sent_at": db.now()},
    )
    return status


def render_digest_email(d: dict) -> tuple[str, str]:
    """Weekly digest, mobile-first: one card per cluster, every blocking criterion explained in plain Italian."""
    from app.services.explain import STAGE_LABELS, STAGE_ORDER, explain

    s = get_settings()
    base = s.public_base_url.rstrip("/")
    reasons_txt = {
        "min_signals": "poco volume", "min_authors": "poche persone diverse", "min_sources": "una sola fonte",
        "min_recent_share": "segnali non recenti", "attack_vector_in": "lamentele su prodotti esistenti", "min_wtp_avg": "poca disponibilità a pagare",
    }
    main = ", ".join(reasons_txt.get(k, k) for k, _ in (d.get("main_reasons") or [])[:2]) or "—"
    subject = f"📬 Validazione · settimana: {d['new_signals_7d']} segnali nuovi, {d['attackable']} problemi attaccabili, {d.get('passed_stage2', 0)} oltre la fase 2"

    def stage_strip(current: str | None) -> str:
        cells = []
        cur_i = STAGE_ORDER.index(current) if current in STAGE_ORDER else 0
        for i, k in enumerate(STAGE_ORDER):
            bg = "#1d4ed8" if i <= cur_i else "#e5e7eb"
            cells.append(f'<td style="height:6px;background:{bg};border-radius:3px;padding:0"></td><td style="width:3px;padding:0"></td>')
        return f'<table role="presentation" style="width:100%;border-collapse:collapse;margin:6px 0 2px"><tr>{"".join(cells)}</tr></table>'

    cards = []
    for r in d["top"]:
        c, o, m = r["cluster"], r["opp"], r["metrics"]
        it = r.get("it") or {}
        av = m.get("dominant_attack_vector") or "—"
        av_it = {"feature_gap": "manca una funzione ai tool esistenti", "no_solution_exists": "nessun tool lo fa, lavoro manuale",
                 "quality_complaint": "lamentele su un prodotto esistente", "price_complaint": "problema di prezzo"}.get(av, av)
        av_color = "#15803d" if av in ("feature_gap", "no_solution_exists") else "#b91c1c" if av == "quality_complaint" else "#6b7280"
        sat = o.get("saturation")
        sat_it = {"blue": "poca concorrenza", "purple": "concorrenza media", "red": "mercato affollato"}.get(sat or "", "concorrenza non ancora analizzata")
        facts = f"{c.get('signal_count') or 0} segnali · {c.get('distinct_authors') or 0} persone · {c.get('distinct_sources') or 0} font{'e' if (c.get('distinct_sources') or 0) == 1 else 'i'}"
        if o.get("sam_eur"):
            facts += f" · mercato raggiungibile {_fmt_eur(o.get('sam_eur'))}"
        blocks = []
        for key, thr in r.get("blocking_detail") or []:
            e = explain(key, thr, m)
            blocks.append(f"""
            <tr><td style="padding:8px 0;border-top:1px solid #f1f5f9">
              <div style="font-size:14px"><b>✘ {escape(e['label'])}</b> &nbsp;<span style="color:#6b7280">oggi {escape(e['current'])} · serve {escape(e['required'])}</span></div>
              <div style="font-size:13px;color:#374151;margin-top:2px">{escape(e['why'])}</div>
              <div style="font-size:13px;color:#1d4ed8;margin-top:2px">→ {escape(e['action'])}</div>
            </td></tr>""")
        nxt = r.get("next_stage")
        cards.append(f"""
        <table role="presentation" style="width:100%;border-collapse:separate;border:1px solid #e5e7eb;border-radius:12px;margin:0 0 16px;background:#ffffff">
          <tr><td style="padding:16px">
            <div style="font-size:17px;font-weight:700;line-height:1.3">{escape(it.get('titolo') or c.get('name') or '')}</div>
            <div style="font-size:14px;color:#374151;margin:6px 0 8px;line-height:1.45">{escape(it.get('spiegazione') or c.get('problem_statement') or '')}</div>
            <div style="font-size:12px;color:#6b7280">{escape(c.get('vertical') or '')} · {escape(c.get('persona') or '')}</div>
            <div style="font-size:12px;color:#6b7280;margin-top:2px">{escape(facts)}</div>
            <div style="font-size:12px;margin-top:6px"><span style="color:{av_color};font-weight:600">● {escape(av_it)}</span> &nbsp;·&nbsp; <span style="color:#6b7280">{escape(sat_it)}</span> &nbsp;·&nbsp; <span style="color:#6b7280">punteggio {r['score']}/100</span></div>
            {stage_strip(r['stage'])}
            <div style="font-size:12px;color:#6b7280">Fase attuale: <b>{escape(STAGE_LABELS.get(r['stage'] or '', r['stage'] or ''))}</b>{(' → prossima: ' + escape(STAGE_LABELS.get(nxt, nxt))) if nxt else ''}</div>
            <div style="font-size:13px;font-weight:600;margin:12px 0 2px">Cosa manca per passare alla fase successiva</div>
            <table role="presentation" style="width:100%;border-collapse:collapse">{''.join(blocks) or '<tr><td style="font-size:13px;color:#15803d;padding:6px 0">Nulla: passa al prossimo controllo.</td></tr>'}</table>
            <div style="margin-top:12px;font-size:13px"><a href="{escape(base)}/opportunities/{escape(c.get('id') or '')}" style="color:#1d4ed8">Dettagli</a> &nbsp;·&nbsp; <a href="{escape(base)}/export/signals.csv?cluster_id={escape(c.get('id') or '')}" style="color:#1d4ed8">Segnali (CSV)</a></div>
          </td></tr>
        </table>""")

    html = f"""
<div style="background:#f8fafc;padding:16px 0">
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:600px;margin:0 auto;padding:0 12px;color:#111827">
  <p style="margin:0 0 4px;font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Validazione start-up · digest settimanale</p>
  <h1 style="margin:0 0 10px;font-size:22px;line-height:1.25">Questa settimana</h1>
  <table role="presentation" style="width:100%;border-collapse:separate;border-spacing:6px 0;margin:0 -6px 12px">
    <tr>
      <td style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px;text-align:center;width:33%"><div style="font-size:22px;font-weight:700">{d['new_signals_7d']}</div><div style="font-size:11px;color:#6b7280">segnali nuovi</div></td>
      <td style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px;text-align:center;width:33%"><div style="font-size:22px;font-weight:700">{d['attackable']}<span style="font-size:13px;color:#6b7280">/{d['total_clusters']}</span></div><div style="font-size:11px;color:#6b7280">problemi attaccabili</div></td>
      <td style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:10px;text-align:center;width:33%"><div style="font-size:22px;font-weight:700">{d.get('passed_stage2', 0)}</div><div style="font-size:11px;color:#6b7280">oltre la fase 2</div></td>
    </tr>
  </table>
  <p style="margin:0 0 18px;font-size:14px;color:#374151;line-height:1.5">
    <b>In breve:</b> {"nessun problema ha ancora superato il filtro 'problema di tanti'. " if not d.get('passed_stage2') else ""}Il motivo principale è: <b>{escape(main)}</b>.
    {"Non è un difetto: il sistema scarta finché non c'è volume da più fonti. Reddit e il tempo risolvono questo." if (d.get('main_reasons') or [("",0)])[0][0] in ("min_signals","min_authors","min_sources","min_recent_share") else ""}
  </p>
  <h2 style="margin:0 0 10px;font-size:15px;color:#374151">I {len(d['top'])} problemi più promettenti</h2>
  {''.join(cards) or '<p style="color:#6b7280">Nessun cluster ancora.</p>'}
  <p style="margin:8px 0 0;font-size:12px;color:#6b7280;line-height:1.5">
    <b>Legenda fasi:</b> 1 segnali → 2 problema di tanti → 3 mercato → 4 concorrenza → 5 founder fit → 6 interviste → 7 pagano? → 8 validata.<br>
    Se un problema in cima è rumore, archivialo (PATCH /opportunities/{{id}} con is_archived=true e il motivo): serve a tarare i filtri.
  </p>
</div></div>"""
    return subject, html
