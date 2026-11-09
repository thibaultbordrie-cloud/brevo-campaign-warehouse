from datetime import date

from brevo_warehouse.alerts import MailSettings, format_email, run_checks, send_email
from brevo_warehouse.ingest import connect, load_campaigns, load_lists

TODAY = date(2026, 10, 21)


def campaign(cid, name, sent=10_000, hard=0, soft=0, complaints=0, clickers=100, unsub=10,
             day="2026-10-20"):
    return {"id": cid, "name": name, "sentDate": f"{day}T10:00:00.000+02:00",
            "statistics": {"globalStats": {"sent": sent, "delivered": sent - hard - soft,
                                           "hardBounces": hard, "softBounces": soft,
                                           "complaints": complaints, "clickers": clickers,
                                           "unsubscriptions": unsub, "uniqueViews": 1000}}}


def warehouse(campaigns, snapshot=TODAY):
    con = connect(":memory:")
    load_campaigns(con, campaigns, snapshot=snapshot)
    return con


def titles(alerts):
    return [a.title for a in alerts]


def test_healthy_day_gives_no_alert():
    assert run_checks(warehouse([campaign(1, "Newsletter OK")]), TODAY) == []


def test_missing_snapshot_today_is_an_alert():
    alerts = run_checks(warehouse([campaign(1, "Newsletter OK")], snapshot=date(2026, 10, 20)), TODAY)
    assert titles(alerts) == ["Chargement du jour absent"]


def test_high_bounce_and_complaints_are_alerts():
    con = warehouse([campaign(1, "Old list", hard=150, soft=100), campaign(2, "Spammy", complaints=20)])
    found = titles(run_checks(con, TODAY))
    assert "Rebonds élevés : Old list" in found and "Plaintes spam : Spammy" in found


def test_more_unsubscribed_than_clickers_is_an_info_listed_after_alerts():
    con = warehouse([campaign(1, "Local event", clickers=5, unsub=30), campaign(2, "Old list", hard=200)])
    alerts = run_checks(con, TODAY)
    assert [a.level for a in alerts] == ["ALERTE", "INFO"]


def test_old_campaigns_and_tiny_tests_are_ignored():
    con = warehouse([campaign(1, "Last month", hard=500, day="2026-09-01"),
                     campaign(2, "Test send", sent=20, hard=10)])
    assert run_checks(con, TODAY) == []


def test_list_losing_subscribers_is_an_alert():
    con = warehouse([campaign(1, "Newsletter OK")])
    load_lists(con, [{"id": 7, "name": "Main list", "totalSubscribers": 100_000}], snapshot=date(2026, 10, 20))
    load_lists(con, [{"id": 7, "name": "Main list", "totalSubscribers": 97_000}], snapshot=TODAY)
    assert titles(run_checks(con, TODAY)) == ["Liste en forte baisse : Main list"]


def test_email_is_built_and_sent_with_starttls():
    alerts = run_checks(warehouse([campaign(1, "Old list", hard=300)]), TODAY)
    subject, body = format_email(alerts, TODAY)
    assert subject.startswith("[brevo-warehouse] 1 alerte(s), 0 info(s)")
    assert "Old list" in body

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def starttls(self, context):
            sent["tls"] = True
        def login(self, user, password):
            sent["login"] = user
        def send_message(self, msg):
            sent["to"] = msg["To"]

    mail = MailSettings("smtp.example", 587, "me@example.com", "pw", "me@example.com", "me@example.com")
    send_email(mail, subject, body, smtp_factory=FakeSMTP)
    assert sent == {"server": ("smtp.example", 587), "tls": True, "login": "me@example.com",
                    "to": "me@example.com"}


def test_missing_mail_settings_are_listed(monkeypatch):
    for k in ["ALERT_SMTP_LOGIN", "ALERT_SMTP_PASSWORD", "ALERT_TO"]:
        monkeypatch.delenv(k, raising=False)
    assert MailSettings.from_env().missing() == ["ALERT_SMTP_LOGIN", "ALERT_SMTP_PASSWORD", "ALERT_TO"]


def test_email_through_the_brevo_api():
    posted = {}

    class FakeClient:
        def post(self, path, payload):
            posted["path"], posted["payload"] = path, payload
            return {"messageId": "x"}

    from brevo_warehouse.alerts import send_email_api
    send_email_api(FakeClient(), "me@example.com", "me@example.com", "Subject", "Body")
    assert posted["path"] == "/smtp/email"
    assert posted["payload"]["to"] == [{"email": "me@example.com"}]
    assert posted["payload"]["textContent"] == "Body"


def test_api_method_only_needs_sender_and_recipient(monkeypatch):
    for k in ["ALERT_SMTP_PASSWORD", "ALERT_FROM"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALERT_SMTP_LOGIN", "me@example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    assert MailSettings.from_env().missing("api") == []


def test_fallback_file_when_the_email_cannot_leave(tmp_path):
    from brevo_warehouse.alerts import write_fallback
    path = write_fallback("[brevo-warehouse] 1 alerte(s)", "Le chargement du matin a échoué", "HTTP 401", tmp_path)
    text = path.read_text(encoding="utf-8")
    assert path.name == "ALERTE brevo-warehouse.txt" and "HTTP 401" in text and "a échoué" in text


def test_simulated_failure_switch(monkeypatch, tmp_path):
    from brevo_warehouse.__main__ import main
    monkeypatch.setenv("WAREHOUSE_SIMULER_PANNE", "1")
    monkeypatch.setenv("WAREHOUSE_DB", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("BREVO_API_KEY", "test")
    assert main(["ingest"]) == 1


def test_email_failure_writes_the_fallback(monkeypatch, tmp_path):
    from brevo_warehouse import __main__ as cli
    monkeypatch.setenv("WAREHOUSE_DB", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("BREVO_API_KEY", "test")
    monkeypatch.setenv("ALERT_SMTP_LOGIN", "me@example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    monkeypatch.setattr(cli, "send_email_api", lambda *a: (_ for _ in ()).throw(RuntimeError("HTTP 401")))
    written = []
    monkeypatch.setattr(cli, "write_alert_file", lambda s, b, r: written.append(r) or tmp_path / "f")
    assert cli.main(["alerts", "--failure", "test"]) == 1
    assert "NON envoyé" in written[0] and "HTTP 401" in written[0]


def test_alert_file_is_written_even_when_the_email_leaves(monkeypatch, tmp_path):
    """22/10/2026: Brevo accepted the email, the receiving server refused it afterwards."""
    from brevo_warehouse import __main__ as cli
    monkeypatch.setenv("WAREHOUSE_DB", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("BREVO_API_KEY", "test")
    monkeypatch.setenv("ALERT_FROM", "alertes@news.example.com")
    monkeypatch.setenv("ALERT_TO", "me@example.com")
    sent, written = [], []
    monkeypatch.setattr(cli, "send_email_api", lambda *a: sent.append(a))
    monkeypatch.setattr(cli, "write_alert_file", lambda s, b, r: written.append(r) or tmp_path / "f")
    assert cli.main(["alerts", "--failure", "test"]) == 0
    assert sent and sent[0][1] == "alertes@news.example.com" and sent[0][5] == "Alertes brevo-warehouse"
    assert written and "confié à Brevo" in written[0]


def test_sender_name_goes_into_the_api_payload():
    from brevo_warehouse.alerts import send_email_api
    calls = []
    class Client:
        def post(self, path, payload): calls.append(payload)
    send_email_api(Client(), "a@news.example.com", "me@example.com", "s", "b", "Alertes entrepôt")
    assert calls[0]["sender"] == {"email": "a@news.example.com", "name": "Alertes entrepôt"}


def test_alert_file_goes_to_a_real_folder_without_being_told_where(monkeypatch, tmp_path):
    """Bug of 22/10/2026: `Path` was not imported, desktop_dir() crashed, no desktop file was ever
    written. Earlier tests always passed a folder, so they never reached that line."""
    from brevo_warehouse import alerts
    monkeypatch.setattr(alerts.Path, "home", classmethod(lambda cls: tmp_path))
    folder = alerts.desktop_dir()
    assert isinstance(folder, alerts.Path) and folder.exists()
    monkeypatch.setattr(alerts, "desktop_dir", lambda: tmp_path)
    path = alerts.write_alert_file("[brevo-warehouse] test", "corps", "email confié à Brevo")
    assert path.parent == tmp_path and "corps" in path.read_text(encoding="utf-8")
