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
    ev_rows = "".join(
        f"<tr><td style='padding:4px 8px;color:#6b7280'>{escape(k)}</td><td style='padding:4px 8px'>{escape(str(v))}</td></tr>"
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
    """Weekly digest: top clusters, what blocks them, one suggested action each."""
    s = get_settings()
    base = s.public_base_url.rstrip("/")
    subject = f"📬 Digest settimanale — {d['total_clusters']} cluster, {d['attackable']} attaccabili, {d['new_signals_7d']} nuovi segnali"
    stage_line = " · ".join(f"{k}: {v}" for k, v in sorted((d.get("stage_counts") or {}).items()))
    rows = []
    for r in d["top"]:
        c, o, m = r["cluster"], r["opp"], r["metrics"]
        av = m.get("dominant_attack_vector") or "—"
        av_color = "#15803d" if av in ("feature_gap", "no_solution_exists") else "#b91c1c" if av == "quality_complaint" else "#6b7280"
        blocking = "<br>".join(escape(v) for v in list(r["blocking"].values())[:3]) or "—"
        action = {
            "problem_clustered": "Aggiungi fonti verticali / attendi volume",
            "market_sized": "Verifica i componenti TAM con una fonte (PUT /market)",
            "competition_checked": "Controlla G2/Capterra a mano e conferma la saturazione",
            "founder_fit_checked": "Scrivi il why-now e il canale (PATCH /opportunities)",
            "interviews_done": "Genera il recruiting pack e fissa 8 interviste",
            "presale_validation": "Landing con prezzo + payment link",
            "validated": "Chiedi 5 pagamenti",
        }.get(r["next_stage"] or "", "—")
        rows.append(f"""
        <tr>
          <td style="padding:10px 8px;border-top:1px solid #e5e7eb;vertical-align:top">
            <b>{escape(c.get('name') or '')}</b><br>
            <span style="font-size:12px;color:#6b7280">{escape(c.get('vertical') or '')} · {escape(c.get('persona') or '')} · {c.get('signal_count') or 0} segnali / {c.get('distinct_authors') or 0} autori</span><br>
            <span style="font-size:12px;color:{av_color};font-weight:600">{escape(av)}</span>
            <span style="font-size:12px;color:#6b7280"> · {_badge(o.get('saturation'))} · SAM {_fmt_eur(o.get('sam_eur'))}</span>
          </td>
          <td style="padding:10px 8px;border-top:1px solid #e5e7eb;vertical-align:top;font-size:13px"><b>{r['score']}</b><br><span style="color:#6b7280">{escape(r['stage'] or '')}</span></td>
          <td style="padding:10px 8px;border-top:1px solid #e5e7eb;vertical-align:top;font-size:12px;color:#374151">{blocking}</td>
          <td style="padding:10px 8px;border-top:1px solid #e5e7eb;vertical-align:top;font-size:12px">{escape(action)}<br>
            <a href="{escape(base)}/opportunities/{escape(c.get('id') or '')}" style="color:#1d4ed8">apri</a></td>
        </tr>""")
    html = f"""
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:760px;margin:0 auto;padding:24px;color:#111827">
  <p style="margin:0 0 4px;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.08em">Validazione start-up · digest settimanale</p>
  <h1 style="margin:0 0 8px;font-size:20px">{d['total_clusters']} cluster · {d['attackable']} con vettore d'attacco · {d['new_signals_7d']} segnali nuovi (7gg)</h1>
  <p style="margin:0 0 16px;font-size:13px;color:#6b7280">Fasi: {escape(stage_line) or '—'}</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr style="font-size:12px;color:#6b7280;text-align:left"><th style="padding:4px 8px">Cluster</th><th style="padding:4px 8px">Score / fase</th><th style="padding:4px 8px">Cosa lo blocca</th><th style="padding:4px 8px">Azione</th></tr>
    {''.join(rows) or '<tr><td colspan="4" style="padding:12px;color:#6b7280">Nessun cluster ancora.</td></tr>'}
  </table>
  <p style="margin:20px 0 0;font-size:12px;color:#9ca3af">Se un cluster in cima è rumore: PATCH /opportunities/{{id}} con is_archived=true e archive_reason — serve a tarare i filtri.</p>
</div>"""
    return subject, html
