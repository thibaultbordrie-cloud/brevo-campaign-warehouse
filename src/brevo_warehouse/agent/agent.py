"""Question in French -> SQL built by rules -> read-only result -> sentence in French.

No AI model: free, works on the work computer, and never guesses. A question that the rules
do not recognise gets an honest "je ne sais pas" with example questions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .guard import GuardError, connect_read_only, run_query
from .parser import EXAMPLES, NotUnderstood, parse


@dataclass
class AgentResult:
    question: str
    sql: str = ""
    understood: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    answer: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.sql) and not self.error


def _fmt(v, unit: str = "") -> str:
    if isinstance(v, float):
        s = f"{v:,.3f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    elif isinstance(v, int):
        s = f"{v:,}"
    elif isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    else:
        return str(v)
    return s.replace(",", " ").replace(".", ",") + (unit if isinstance(v, float) else "")


MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def _sentence(understood: str, columns: list[str], rows: list[tuple], unit: str) -> str:
    if columns and columns[0] == "mois":
        rows = [(MOIS[r[0] - 1] if isinstance(r[0], int) and 1 <= r[0] <= 12 else r[0],) + tuple(r[1:])
                for r in rows]
    if not rows:
        return f"{understood[:1].upper()}{understood[1:]} : aucun résultat."
    if len(rows) == 1 and len(rows[0]) == 1:
        return f"{understood[:1].upper()}{understood[1:]} : {_fmt(rows[0][0], unit)}."
    lines = [f"{understood[:1].upper()}{understood[1:]} :"]
    for row in rows[:20]:
        lines.append("  - " + " · ".join(_fmt(v, unit if i == len(row) - 1 else "") for i, v in enumerate(row)))
    if len(rows) > 20:
        lines.append(f"  ... {len(rows)} lignes")
    return "\n".join(lines)


def _comparison(intent, row) -> str:
    a_label, b_label = intent.parts
    a, b, concerned, total = (v or 0 for v in row)
    verdict = "Oui" if a > b else "Non"
    text = (f"{verdict} : {_fmt(a)} {a_label} contre {_fmt(b)} {b_label} au total "
            f"({intent.understood.split(' — ', 1)[1] if ' — ' in intent.understood else 'toutes campagnes'}).")
    if concerned:
        text += f" Mais {_fmt(concerned)} campagne(s) sur {_fmt(total)} ont plus de {a_label} que de {b_label}."
    else:
        text += f" Aucune des {_fmt(total)} campagnes n'a plus de {a_label} que de {b_label}."
    return text


def ask(question: str, db_path: Path | str | None = None, con=None) -> AgentResult:
    own = con is None
    if own:
        from ..config import load_settings
        con = connect_read_only(db_path or load_settings().db_path)
    result = AgentResult(question)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM dim_list").fetchall()]
        intent = parse(question, names)
        result.sql, result.understood = intent.sql, intent.understood
        result.columns, result.rows = run_query(con, intent.sql)
        if intent.kind == "comparison" and result.rows and len(result.rows[0]) == 4:
            result.answer = _comparison(intent, result.rows[0])
        else:
            result.answer = _sentence(intent.understood, result.columns, result.rows, intent.unit)
    except NotUnderstood as exc:
        result.error = str(exc)
        result.answer = (f"Je ne sais pas répondre à cette question. {exc}\n"
                         "Exemples de questions comprises :\n" + "\n".join(f"  - {e}" for e in EXAMPLES))
    except (GuardError, Exception) as exc:            # never expected: the rules build the SQL
        result.error = f"{type(exc).__name__}: {exc}"
        result.answer = "La requête construite a été refusée ou a échoué : " + result.error
    finally:
        if own:
            con.close()
    return result
