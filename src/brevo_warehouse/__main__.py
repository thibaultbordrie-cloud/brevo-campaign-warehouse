"""Command line: python -m brevo_warehouse <command>

  init              create the database and its tables
  ingest            read sent campaigns and contact lists from Brevo and load them
  kpis [--limit N]  print the latest KPIs per campaign
  query FILE.sql    run a SQL file and print the result
  report            run every query in sql/analyses and save the results in reports/
  alerts [--dry-run] [--failure TEXT]  run the data checks and email the owner if needed
  secret set|check|delete [NAME]       keys in the Windows Credential Manager
  ask "QUESTION"    question assistant (rules, no AI): French question -> SQL -> answer
  eval              score the assistant on its test questions (fictional data)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .client import BrevoClient, BrevoError
from .config import load_settings
from .ingest import connect, load_campaigns, load_lists
from .report import build_report
import os

from .alerts import (Alert, MailSettings, format_email, run_checks, send_email, send_email_api,
                     write_alert_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brevo_warehouse")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("ingest")
    k = sub.add_parser("kpis")
    k.add_argument("--limit", type=int, default=20)
    q = sub.add_parser("query")
    q.add_argument("file", type=Path)
    r = sub.add_parser("report")
    r.add_argument("--sql-dir", type=Path, default=Path("sql/analyses"))
    r.add_argument("--out-dir", type=Path, default=Path("reports"))
    a = sub.add_parser("alerts")
    a.add_argument("--dry-run", action="store_true", help="print the email instead of sending it")
    a.add_argument("--failure", default="", help="report a failed run (no checks are made)")
    q2 = sub.add_parser("ask")
    q2.add_argument("question")
    sub.add_parser("eval")
    s = sub.add_parser("secret")
    s.add_argument("action", choices=["set", "check", "delete"])
    s.add_argument("name", nargs="?", default="")
    args = parser.parse_args(argv)

    if args.cmd == "secret":
        return _secret(args)
    if args.cmd == "eval":
        return _eval()

    settings = load_settings()
    if args.cmd == "ask":
        return _ask(args, settings)
    if args.cmd == "alerts":
        return _alerts(args, settings)
    con = connect(settings.db_path)

    if args.cmd == "init":
        print(f"Database ready: {settings.db_path}")
        return 0
    if args.cmd == "ingest":
        try:
            if os.environ.get("WAREHOUSE_SIMULER_PANNE"):
                # Interrupteur de test (programme, bloc 4) : provoque une panne pour vérifier l'alerte.
                raise BrevoError("Panne simulée volontairement (variable WAREHOUSE_SIMULER_PANNE).")
            client = BrevoClient(settings.api_key, settings.base_url, settings.verify_ssl, settings.timeout)
            n = load_campaigns(con, client.iter_email_campaigns())
            print(f"Loaded {n} campaigns into {settings.db_path}")
            m = load_lists(con, client.iter_contact_lists())
            print(f"Loaded {m} contact lists into {settings.db_path}")
        except BrevoError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1
        return 0
    if args.cmd == "kpis":
        con.sql(f"SELECT * FROM v_campaign_kpis ORDER BY send_date DESC NULLS LAST LIMIT {int(args.limit)}").show()
        return 0
    if args.cmd == "query":
        con.sql(args.file.read_text(encoding="utf-8")).show()
        return 0
    if args.cmd == "report":
        args.out_dir.mkdir(parents=True, exist_ok=True)
        out = args.out_dir / f"analyses_{date.today().isoformat()}.txt"
        out.write_text(build_report(con, args.sql_dir), encoding="utf-8")
        print(f"Report saved: {out.resolve()}")
        return 0
    return 2


def _alerts(args, settings) -> int:
    if args.failure:
        alerts = [Alert("ALERTE", "Le chargement du matin a échoué", args.failure)]
    else:
        con = connect(settings.db_path)
        alerts = run_checks(con)
        con.close()
    if not alerts:
        print("Checks OK: nothing to report.")
        return 0
    subject, body = format_email(alerts)
    if args.dry_run:
        print(subject, body, sep="\n\n")
        return 0
    mail = MailSettings.from_env()
    method = os.environ.get("ALERT_METHOD", "api").strip().lower()
    # The desktop file is ALWAYS written: an email accepted by Brevo can still be refused
    # later by the receiving server (seen on 22/10/2026: soft bounce "Access denied").
    if mail.missing(method):
        status = "email NON envoyé, réglages manquants dans .env : " + ", ".join(mail.missing(method))
        print(f"[ERROR] {status}", file=sys.stderr)
        print(f"Alert file written: {write_alert_file(subject, body, status)}")
        return 1
    try:
        if method == "smtp":
            send_email(mail, subject, body)
        else:
            client = BrevoClient(settings.api_key, settings.base_url, settings.verify_ssl, settings.timeout)
            send_email_api(client, mail.sender, mail.recipient, subject, body, mail.sender_name)
    except Exception as exc:  # never crash the daily run because of the email
        status = f"email NON envoyé ({method}) : {str(exc)[:300]}"
        print(f"[ERROR] {status}", file=sys.stderr)
        print(f"Alert file written: {write_alert_file(subject, body, status)}")
        return 1
    print(f"Email sent to {mail.recipient}: {subject}")
    print(f"Alert file written: {write_alert_file(subject, body, f'email confié à Brevo pour {mail.recipient}')}")
    return 0


def _ask(args, settings) -> int:
    from .agent import ask
    res = ask(args.question, settings.db_path)
    print(res.answer)
    if res.sql:
        print("\nRequête utilisée (lecture seule) :\n" + res.sql)
    return 0 if res.ok else 1


def _eval() -> int:
    from .agent import evaluate
    text = evaluate.report(evaluate.run())
    out = Path("reports") / f"eval_assistant_{date.today().isoformat()}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text.split("| Question")[0])
    print(f"Rapport complet : {out.resolve()}")
    return 0


def _secret(args) -> int:
    from getpass import getpass
    from .config import PROJECT_ROOT
    from .vault import SECRET_NAMES, VaultError, check, default_store
    store = default_store()
    if args.action == "check":
        lines, clean = check(PROJECT_ROOT / ".env", store)
        print("\n".join(lines))
        if not store:
            print("(coffre Windows indisponible sur cette machine)")
        return 0 if clean else 1
    if args.name not in SECRET_NAMES:
        print(f"Nom attendu : {' ou '.join(SECRET_NAMES)}", file=sys.stderr)
        return 2
    if not store:
        print("Coffre Windows indisponible sur cette machine.", file=sys.stderr)
        return 1
    try:
        if args.action == "delete":
            print("Supprimé." if store.delete(args.name) else "Rien à supprimer.")
            return 0
        value = getpass(f"Colle la valeur de {args.name} (rien ne s'affiche, c'est normal) puis Entrée : ").strip()
        if not value:
            print("Valeur vide : rien n'est enregistré.", file=sys.stderr)
            return 1
        store.write(args.name, value)
    except VaultError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"{args.name} enregistré dans le coffre Windows ({len(value)} caractères, se termine par ...{value[-4:]}).")
    return 0

if __name__ == "__main__":
    sys.exit(main())
