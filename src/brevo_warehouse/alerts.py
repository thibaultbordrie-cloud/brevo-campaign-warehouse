"""Daily data checks on the warehouse, and an email when something needs attention.

Each check is a small SQL query on the latest snapshots. A check returns zero or more Alert
objects; if there is at least one, a single email summarises them all. Thresholds are
constants below so they can be discussed and changed in one place.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

import duckdb

RECENT_DAYS = 3                 # only campaigns sent in the last 3 days are checked
MIN_SENT = 1000                 # ignore tiny tests
MAX_BOUNCE_RATE = 2.0           # % of sent; above, mailbox providers start to distrust the sender
MAX_HARD_BOUNCE_RATE = 1.0      # % of sent; invalid addresses, usually an old or imported list
MAX_COMPLAINT_RATE = 0.1        # % of delivered; Gmail and Yahoo ask senders to stay below 0.1 %
MAX_LIST_DROP_RATE = 1.0        # % of subscribers lost by a list since the previous snapshot


@dataclass(frozen=True)
class Alert:
    level: str      # "ALERTE" (act now) or "INFO" (look when you can)
    title: str
    detail: str


def _recent(con, sql: str, today: date) -> list[tuple]:
    since = today - timedelta(days=RECENT_DAYS)
    return con.execute(sql, [since, MIN_SENT]).fetchall()


_LATEST = """
    WITH latest AS (
        SELECT f.*, ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY snapshot_date DESC) AS rn
        FROM fact_campaign_stats f
    )
    SELECT c.name, CAST(c.sent_at AS DATE) AS send_date, l.sent, l.delivered,
           l.hard_bounces, l.soft_bounces, l.complaints, l.clickers, l.unsubscriptions
    FROM latest l JOIN dim_campaign c USING (campaign_id)
    WHERE l.rn = 1 AND CAST(c.sent_at AS DATE) >= ? AND l.sent >= ?
    ORDER BY c.sent_at DESC
"""


def check_freshness(con, today: date) -> list[Alert]:
    last = con.execute("SELECT MAX(snapshot_date) FROM fact_campaign_stats").fetchone()[0]
    if last is None:
        return [Alert("ALERTE", "Entrepôt vide", "Aucune photo de campagne n'a encore été chargée.")]
    if last < today:
        return [Alert("ALERTE", "Chargement du jour absent",
                      f"Dernière photo : {last:%d/%m/%Y}. Le chargement de ce matin n'a pas eu lieu.")]
    return []


def check_deliverability(con, today: date) -> list[Alert]:
    alerts = []
    for name, send_date, sent, delivered, hard, soft, complaints, _, _ in _recent(con, _LATEST, today):
        bounce = 100.0 * (hard + soft) / sent
        hard_rate = 100.0 * hard / sent
        if bounce > MAX_BOUNCE_RATE or hard_rate > MAX_HARD_BOUNCE_RATE:
            alerts.append(Alert("ALERTE", f"Rebonds élevés : {name}",
                                f"Envoyée le {send_date:%d/%m}, {sent:,} envois : {bounce:.1f} % de rebonds "
                                f"dont {hard_rate:.1f} % d'adresses invalides (seuils {MAX_BOUNCE_RATE} % "
                                f"et {MAX_HARD_BOUNCE_RATE} %). Vérifier la liste utilisée."))
        if delivered and 100.0 * complaints / delivered > MAX_COMPLAINT_RATE:
            alerts.append(Alert("ALERTE", f"Plaintes spam : {name}",
                                f"{complaints} plaintes pour {delivered:,} délivrés "
                                f"({100.0 * complaints / delivered:.2f} %, seuil {MAX_COMPLAINT_RATE} %)."))
    return alerts


def check_unsubscribes(con, today: date) -> list[Alert]:
    return [Alert("INFO", f"Plus de désinscrits que de cliqueurs : {name}",
                  f"Envoyée le {send_date:%d/%m} : {unsub} désinscrits pour {clickers} cliqueurs.")
            for name, send_date, _, _, _, _, _, clickers, unsub in _recent(con, _LATEST, today)
            if unsub > clickers]


def check_list_drops(con, today: date) -> list[Alert]:
    rows = con.execute("""
        WITH s AS (
            SELECT v.list_id, v.snapshot_date, v.subscribers,
                   LAG(v.subscribers) OVER (PARTITION BY v.list_id ORDER BY v.snapshot_date) AS previous
            FROM v_list_size v          -- falls back to unique subscribers when Brevo's total is 0
        )
        SELECT l.name, s.previous, s.subscribers
        FROM s JOIN dim_list l USING (list_id)
        WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM fact_list_size)
          AND s.previous > 0
          AND 100.0 * (s.previous - s.subscribers) / s.previous > ?
    """, [MAX_LIST_DROP_RATE]).fetchall()
    return [Alert("ALERTE", f"Liste en forte baisse : {name}",
                  f"{previous:,} → {now:,} abonnés ({100.0 * (previous - now) / previous:.1f} % "
                  f"en un jour, seuil {MAX_LIST_DROP_RATE} %).")
            for name, previous, now in rows]


CHECKS = [check_freshness, check_deliverability, check_unsubscribes, check_list_drops]


def run_checks(con: duckdb.DuckDBPyConnection, today: date | None = None) -> list[Alert]:
    today = today or date.today()
    alerts: list[Alert] = []
    for check in CHECKS:
        alerts.extend(check(con, today))
    return sorted(alerts, key=lambda a: a.level != "ALERTE")   # ALERTE first


def format_email(alerts: list[Alert], today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    n_alert = sum(a.level == "ALERTE" for a in alerts)
    subject = (f"[brevo-warehouse] {n_alert} alerte(s), {len(alerts) - n_alert} info(s) "
               f"- {today:%d/%m/%Y}")
    lines = [f"Contrôles du {today:%d/%m/%Y}.", ""]
    for a in alerts:
        lines += [f"[{a.level}] {a.title}", f"    {a.detail}", ""]
    lines.append("Message automatique de brevo-warehouse (envoyé uniquement à son propriétaire).")
    return subject, "\n".join(lines)


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    login: str
    password: str
    sender: str
    recipient: str
    sender_name: str = "Alertes brevo-warehouse"

    @classmethod
    def from_env(cls) -> "MailSettings":
        login = os.environ.get("ALERT_SMTP_LOGIN", "")
        return cls(
            host=os.environ.get("ALERT_SMTP_HOST", "smtp-relay.brevo.com"),
            port=int(os.environ.get("ALERT_SMTP_PORT", "587")),
            login=login,
            password=os.environ.get("ALERT_SMTP_PASSWORD", ""),
            sender=os.environ.get("ALERT_FROM", login),
            recipient=os.environ.get("ALERT_TO", ""),
            sender_name=os.environ.get("ALERT_FROM_NAME", "Alertes brevo-warehouse"),
        )

    def missing(self, method: str = "smtp") -> list[str]:
        if method == "api":
            names = {"ALERT_FROM or ALERT_SMTP_LOGIN": self.sender, "ALERT_TO": self.recipient}
        else:
            names = {"ALERT_SMTP_LOGIN": self.login, "ALERT_SMTP_PASSWORD": self.password,
                     "ALERT_TO": self.recipient}
        return [k for k, v in names.items() if not v]


def send_email_api(client, sender: str, recipient: str, subject: str, body: str,
                   sender_name: str = "Alertes brevo-warehouse") -> None:
    """Send through Brevo's transactional email API, over HTTPS.

    Used by default: corporate networks often block outgoing SMTP (port 587) but allow
    HTTPS. The sender must be a sender verified in the Brevo account.
    """
    client.post("/smtp/email", {
        "sender": {"email": sender, "name": sender_name},
        "to": [{"email": recipient}],
        "subject": subject,
        "textContent": body,
    })


def send_email(mail: MailSettings, subject: str, body: str, smtp_factory=smtplib.SMTP) -> None:
    """Send through an SMTP relay (only if ALERT_METHOD=smtp: port 587 must be open)."""
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, mail.sender, mail.recipient
    msg.set_content(body)
    from .client import use_system_certificates
    use_system_certificates()   # corporate network: trust the Windows certificate store
    with smtp_factory(mail.host, mail.port, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(mail.login, mail.password)
        smtp.send_message(msg)


def desktop_dir() -> Path:
    """Visible Windows desktop (also when redirected to OneDrive); home folder elsewhere."""
    try:
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, buf)   # CSIDL_DESKTOPDIRECTORY
        if buf.value:
            return Path(buf.value)
    except Exception:
        pass
    return Path.home()


def write_alert_file(subject: str, body: str, status: str, folder: Path | None = None) -> Path:
    """Second channel, independent of email: a file on the desktop that cannot be missed.

    Written for every alert, whatever happened to the email: Brevo may accept a message
    that the receiving server refuses afterwards, and nothing tells the program.
    """
    folder = folder or desktop_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ALERTE brevo-warehouse.txt"
    path.write_text(f"{subject}\n\nEmail : {status}\n\n{body}\n", encoding="utf-8")
    return path


write_fallback = write_alert_file   # former name
