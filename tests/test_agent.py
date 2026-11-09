"""Question assistant (rules only): guard rails, understanding, honest refusals, scores.

The scores of the evaluation are tests too: if a change to the rules breaks a question that
used to work, CI goes red.
"""
import json
from pathlib import Path

import pytest

from brevo_warehouse.agent import evaluate
from brevo_warehouse.agent.agent import ask
from brevo_warehouse.agent.guard import GuardError, check_sql, connect_read_only, run_query
from brevo_warehouse.agent.parser import normalise, parse

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    path = tmp_path_factory.mktemp("assistant") / "demo.duckdb"
    evaluate.build_demo(path)
    con = connect_read_only(path)
    yield con
    con.close()


# ---------- guard ----------
@pytest.mark.parametrize("sql", [
    "DELETE FROM dim_campaign",
    "SELECT 1; DROP TABLE dim_campaign",
    "ATTACH 'x.db'",
    "SELECT * FROM read_csv('C:/Users/secret.csv')",
    "COPY dim_campaign TO 'out.csv'",
    "INSTALL httpfs",
    "PRAGMA database_list",
    "SELECT getenv('BREVO_API_KEY')",
    "",
])
def test_guard_refuses_anything_but_one_select(sql):
    with pytest.raises(GuardError):
        check_sql(sql)


def test_guard_accepts_select_with_and_forbidden_words_inside_strings():
    assert check_sql("WITH a AS (SELECT 1 AS x) SELECT x FROM a;").startswith("WITH")
    check_sql("SELECT COUNT(*) FROM v_campaign_kpis WHERE name = 'delete; drop'")
    check_sql("SELECT last_update, offset_days FROM t")


def test_connection_cannot_write_or_read_files(demo):
    with pytest.raises(Exception):
        demo.execute("CREATE TABLE hack (a INT)")
    with pytest.raises(Exception):
        demo.execute("SELECT * FROM read_csv('pyproject.toml')")


def test_results_are_capped(demo):
    cols, rows = run_query(demo, "SELECT * FROM range(100000)")
    assert len(rows) == 200


# ---------- understanding ----------
def test_normalise_removes_accents_case_and_abbreviations():
    assert normalise("Délivrés « nb » d’E-mails ?") == "delivres nombre d emails"


def test_answers_in_french_with_what_was_understood(demo):
    res = ask("Combien de campagnes locales en mars 2026 ?", con=demo)
    assert res.ok and res.rows == [(4,)]
    assert res.answer == "Nombre de campagnes — périmètre local, mars 2026 : 4."


def test_user_text_never_reaches_the_sql(demo):
    """A list name is taken from the database, never pasted from the question."""
    intent = parse("Combien d'abonnés dans la liste x'; DROP TABLE dim_list; -- ?", ["Fictional list 1"])
    assert "DROP" not in intent.sql
    assert ask("Abonnés de Fictional list 1 ?", con=demo).rows[0][1] > 0


@pytest.mark.parametrize("question", [
    "Supprime toutes les campagnes de mars",
    "Quel temps fera-t-il demain ?",
    "Combien de points a la cliente Dupont ?",
    "",
])
def test_says_it_does_not_know_instead_of_guessing(demo, question):
    res = ask(question, con=demo)
    assert not res.ok and res.answer.startswith("Je ne sais pas répondre")
    assert "Exemples de questions" in res.answer


def test_every_generated_query_obeys_the_guard(demo):
    for path in evaluate.SETS:
        for q in json.loads(path.read_text(encoding="utf-8")).get("questions", []):
            res = ask(q["question"], con=demo)
            if res.sql:
                check_sql(res.sql)


# ---------- evaluation ----------
def test_scoring_is_tolerant_on_names_columns_and_rounding_but_not_on_values():
    assert evaluate.matches([("NATIONAL", 0.704), ("LOCAL", 0.91)], [("LOCAL", 0.91), ("NATIONAL", 0.7)])
    assert evaluate.matches([(42, "Survey 41", 12.3)], [("survey 41",)])
    assert not evaluate.matches([(61,)], [(60,)])
    assert not evaluate.matches([("a", 2), ("b", 1)], [("b", 1), ("a", 2)], order_matters=True)


def test_test_sets_are_complete_and_their_references_run(demo):
    main = json.loads(evaluate.SETS[0].read_text(encoding="utf-8"))["questions"]
    variants = json.loads(evaluate.SETS[1].read_text(encoding="utf-8"))
    assert len(main) == 30 and {q["level"] for q in main} == {"simple", "complex"}
    assert len(variants["questions"]) == 23 and len(variants["out_of_scope"]) == 6
    for q in main + variants["questions"]:
        check_sql(q["reference_sql"])
        assert demo.execute(q["reference_sql"]).fetchall(), q["id"]


def test_scores_do_not_go_backwards():
    scores = evaluate.run()
    by_level = {}
    for s in scores:
        by_level.setdefault(s.level, []).append(s.correct)
    assert {k: (sum(v), len(v)) for k, v in by_level.items()} == {
        "simple": (15, 15), "complex": (15, 15), "variant": (23, 23), "out_of_scope": (6, 6)}
    assert "**simples** : 15/15" in evaluate.report(scores)


def test_no_ai_provider_and_no_key_in_the_assistant():
    code = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src" / "brevo_warehouse" / "agent").glob("*.py"))
    for word in ("anthropic", "openai", "ollama", "api_key", "requests"):
        assert word not in code.lower(), word


def test_yes_no_comparison_is_answered_with_both_totals_not_with_one(demo):
    """Real-data miss of 22/10/2026: the question got the total of unsubscriptions only."""
    res = ask("est-ce que les campagnes locales font plus de désinscrits que de clics", con=demo)
    assert res.ok and len(res.rows[0]) == 4 and "contre" in res.understood


def test_other_yes_no_questions_are_refused_not_guessed(demo):
    assert not ask("est-ce que le taux d'ouverture est bon ?", con=demo).ok


def test_months_are_named_in_the_answer(demo):
    assert "janvier" in ask("nombre de campagnes par mois en 2026", con=demo).answer
