"""Measure the question assistant on its test sets, always on the FICTIONAL demo warehouse.

    evals/questions.json            30 questions (15 simple, 15 complex), written with the rules
    evals/questions_variants.json   20 paraphrases written AFTER the rules + 6 out-of-scope questions

An answer is correct when the result contains the values of the reference query (column names
and extra columns do not matter; numbers match within 0.5 %, or 0.01 for small values; order
only when the question asks for it). An out-of-scope question is correct when it is refused.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .agent import ask
from .guard import connect_read_only

ROOT = Path(__file__).resolve().parents[3]
SETS = [ROOT / "evals" / "questions.json", ROOT / "evals" / "questions_variants.json"]


def _norm(v):
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return float(v)
    if hasattr(v, "__float__") and not isinstance(v, str):      # Decimal
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return str(v).strip().lower()


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(0.01, 0.005 * abs(b))
    return a == b


def _row_contains(row, ref_row) -> bool:
    pool = [_norm(v) for v in row]
    for want in (_norm(v) for v in ref_row):
        for i, have in enumerate(pool):
            if _same(have, want):
                del pool[i]
                break
        else:
            return False
    return True


def matches(rows, ref_rows, order_matters: bool = False) -> bool:
    if len(rows) != len(ref_rows):
        return False
    if order_matters:
        return all(_row_contains(a, r) for a, r in zip(rows, ref_rows))
    remaining = list(rows)
    for r in ref_rows:
        for i, a in enumerate(remaining):
            if _row_contains(a, r):
                del remaining[i]
                break
        else:
            return False
    return True


@dataclass
class Score:
    id: str
    level: str
    question: str
    correct: bool
    understood: str
    sql: str


def build_demo(path: Path) -> None:
    spec = importlib.util.spec_from_file_location("make_demo_db", ROOT / "scripts" / "make_demo_db.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    demo.main(str(path))


def run(sets=SETS) -> list[Score]:
    scores = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo.duckdb"
        build_demo(db)
        con = connect_read_only(db)
        try:
            for path in sets:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                for q in data.get("questions", []):
                    ref = con.execute(q["reference_sql"]).fetchall()
                    res = ask(q["question"], con=con)
                    ok = res.ok and matches(res.rows, ref, q.get("order_matters", False))
                    scores.append(Score(q["id"], q["level"], q["question"], ok,
                                        res.understood or res.error, res.sql))
                for q in data.get("out_of_scope", []):
                    res = ask(q["question"], con=con)
                    scores.append(Score(q["id"], "out_of_scope", q["question"], not res.ok,
                                        res.error or res.understood, res.sql))
        finally:
            con.close()
    return scores


LEVELS = [("simple", "simples"), ("complex", "complexes"),
          ("variant", "reformulations écrites après les règles"),
          ("out_of_scope", "hors sujet, à refuser")]


def report(scores: list[Score]) -> str:
    lines = [f"# Évaluation de l'assistant à questions — {date.today():%d/%m/%Y}", "",
             "Règles seulement, aucun modèle d'IA. Données fictives.", ""]
    for key, label in LEVELS:
        sub = [s for s in scores if s.level == key]
        if sub:
            lines.append(f"- **{label}** : {sum(s.correct for s in sub)}/{len(sub)}")
    lines += ["", "| Question | Niveau | Juste | Compris comme |", "|---|---|---|---|"]
    for s in scores:
        lines.append(f"| {s.id} {s.question.replace('|', '/')} | {s.level} | "
                     f"{'oui' if s.correct else '**non**'} | {s.understood.replace('|', '/')} |")
    return "\n".join(lines) + "\n"
