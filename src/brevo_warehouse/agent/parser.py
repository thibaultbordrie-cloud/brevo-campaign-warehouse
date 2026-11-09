"""French question -> structured intent -> SQL, with rules only (no AI model, no cost).

The question is normalised (lower case, no accents), then read in a fixed order:
which subject (campaigns, lists, snapshots), which measure (open rate, deliveries...),
which calculation (count, total, average, global rate, best / worst, change), which filters
(local / national, month, half-year, threshold, store closures) and which grouping.
Values that end up in the SQL come only from fixed lists or from names that exist in the
database: the user's text is never pasted into the query.

Anything not recognised raises NotUnderstood with example questions: the assistant says
"I don't know" instead of guessing.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


class NotUnderstood(ValueError):
    pass


EXAMPLES = [
    "Combien de campagnes locales en mars 2026 ?",
    "Quel est le taux d'ouverture moyen des campagnes nationales ?",
    "Quelles sont les 5 campagnes qui ont le plus de délivrés ?",
    "Quel est le taux de clic moyen par périmètre ?",
    "Combien d'abonnés compte aujourd'hui la liste « Nom de la liste » ?",
    "Quelle est la date de la dernière photo des statistiques ?",
]

MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
          "septembre", "octobre", "novembre", "decembre"]
NUMBERS = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "quinze": 15, "vingt": 20}


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    words: tuple
    column: str = ""           # per-campaign column (view k or latest snapshot f)
    rate: bool = False
    decimals: int = 2
    num: str = ""              # global rate = 100 * SUM(num) / SUM(den)
    den: str = ""


# Order matters: the first metric found in the question wins (rates before raw counts).
METRICS = [
    Metric("unsub_rate", "taux de désinscription", ("taux de desinscription", "taux desinscription"),
           "k.unsub_rate_pct", True, 3, "f.unsubscriptions", "k.delivered"),
    Metric("open_rate", "taux d'ouverture", ("taux d ouverture", "taux ouverture"),
           "k.open_rate_pct", True, 2, "f.unique_views", "k.delivered"),
    Metric("click_rate", "taux de clic", ("taux de clic",),
           "k.click_rate_pct", True, 2, "f.clickers", "k.delivered"),
    Metric("ctor", "CTOR", ("ctor", "clic sur ouverture", "taux de reactivite"),
           "k.ctor_pct", True, 2, "f.clickers", "f.unique_views"),
    Metric("soft_rate", "taux de soft bounces", ("taux de soft bounce", "taux global de soft bounce"),
           "", True, 2, "f.soft_bounces", "f.sent"),
    Metric("hard_rate", "taux de hard bounces", ("taux de hard bounce", "taux global de hard bounce"),
           "", True, 2, "f.hard_bounces", "f.sent"),
    Metric("complaints", "plaintes pour spam", ("plainte",), "f.complaints"),
    Metric("hard_bounces", "hard bounces", ("hard bounce",), "f.hard_bounces"),
    Metric("soft_bounces", "soft bounces", ("soft bounce",), "f.soft_bounces"),
    Metric("unsubscriptions", "désinscrits", ("desinscrit", "desinscription"), "f.unsubscriptions"),
    Metric("clickers", "cliqueurs", ("cliqueur",), "f.clickers"),
    Metric("openers", "ouvreurs uniques", ("ouvreur",), "f.unique_views"),
    Metric("delivered", "e-mails délivrés", ("delivre",), "k.delivered"),
]


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[’'`«»\"?!;:()]", " ", text)
    text = text.replace("e-mail", "email").replace("bounces", "bounce")
    text = re.sub(r"\bnb\b", "nombre", text)
    return re.sub(r"\s+", " ", text).strip()


def has(q: str, *patterns: str) -> bool:
    return any(re.search(p, q) for p in patterns)


@dataclass
class Intent:
    sql: str
    understood: str                       # what the assistant understood, in French
    unit: str = ""                        # " %" for rates
    parts: list = field(default_factory=list)
    kind: str = ""                        # "comparison": answered by a yes / no sentence


# ---------- helpers ----------------------------------------------------------------------
LATEST = ("latest AS (SELECT * FROM fact_campaign_stats "
          "QUALIFY ROW_NUMBER() OVER (PARTITION BY campaign_id ORDER BY snapshot_date DESC) = 1)")
BASE = f"WITH {LATEST} SELECT {{select}} FROM v_campaign_kpis k JOIN latest f USING (campaign_id)"


def find_metric(q: str) -> Metric | None:
    for m in METRICS:
        if any(w in q for w in m.words):
            return m
    return None


def find_n(q: str) -> int:
    m = re.search(r"\b(?:les|top)\s+(\d+|" + "|".join(NUMBERS) + r")\b", q)
    if not m:
        return 1
    v = m.group(1)
    return int(v) if v.isdigit() else NUMBERS[v]


def period_filters(q: str, parts: list) -> list[str]:
    where = []
    year_m = re.search(r"\b(20\d\d)\b", q)
    year = int(year_m.group(1)) if year_m else None
    month_m = re.search(r"\b(" + "|".join(MONTHS) + r")\s+(20\d\d)\b", q)
    if has(q, r"premier semestre", r"janvier a juin") and year:
        where.append(f"k.send_date >= DATE '{year}-01-01' AND k.send_date < DATE '{year}-07-01'")
        parts.append(f"premier semestre {year}")
    elif has(q, r"(second|deuxieme|2e) semestre", r"juillet a decembre") and year:
        where.append(f"k.send_date >= DATE '{year}-07-01' AND k.send_date < DATE '{year + 1}-01-01'")
        parts.append(f"second semestre {year}")
    elif month_m:
        mo, yr = MONTHS.index(month_m.group(1)) + 1, int(month_m.group(2))
        nxt = f"{yr + 1}-01-01" if mo == 12 else f"{yr}-{mo + 1:02d}-01"
        where.append(f"k.send_date >= DATE '{yr}-{mo:02d}-01' AND k.send_date < DATE '{nxt}'")
        parts.append(f"{month_m.group(1)} {yr}")
    elif year:
        where.append(f"year(k.send_date) = {year}")
        parts.append(f"année {year}")
    return where


def campaign_filters(q: str, metric: Metric | None, parts: list) -> tuple[list[str], bool]:
    """WHERE clauses and whether results are grouped by scope."""
    where = []
    by_scope = has(q, r"par perimetre", r"chaque perimetre", r"locales? et nationales?",
                   r"nationales? et locales?", r"local et national", r"national et local")
    if not by_scope:
        if has(q, r"\blocal(e|es|s|aux)?\b"):
            where.append("k.scope = 'LOCAL'")
            parts.append("périmètre local")
        elif has(q, r"\bnationa(l|le|les|ux)\b"):
            where.append("k.scope = 'NATIONAL'")
            parts.append("périmètre national")
    if "fermeture" in q:
        where.append("lower(k.name) LIKE '%fermeture%'")
        parts.append("campagnes de fermeture de magasin")
    where += period_filters(q, parts)
    th = re.search(r"\b(superieur|plus|au.dessus|inferieur|moins|en.dessous)\s+(?:a|de|d)?\s*"
                   r"(\d+(?:[.,]\d+)?)\s*(?:%|pour ?cent)", q)
    if th and metric and metric.rate and metric.column:
        op = ">" if th.group(1) in ("superieur", "plus") or th.group(1).startswith("au") else "<"
        value = float(th.group(2).replace(",", "."))
        where.append(f"{metric.column} {op} {value}")
        parts.append(f"{metric.label} {op} {value:g} %")
    return where, by_scope


def _where(clauses: list[str]) -> str:
    return (" WHERE " + " AND ".join(clauses)) if clauses else ""


# ---------- subjects ---------------------------------------------------------------------
def lists_intent(q: str, list_names: list[str]) -> Intent | None:
    if "liste noire" in q and has(q, r"var(ie|iation)", r"evolu", r"entre la premiere"):
        return Intent("SELECT SUM(last) - SUM(first) AS variation FROM (SELECT "
                      "arg_max(total_blacklisted, snapshot_date) AS last, "
                      "arg_min(total_blacklisted, snapshot_date) AS first FROM fact_list_size GROUP BY list_id)",
                      "variation du nombre de contacts en liste noire, toutes listes, première → dernière photo")
    named = [n for n in sorted(list_names, key=len, reverse=True) if normalise(n) and normalise(n) in q]
    if named and "abonne" in q:
        name = named[0].replace("'", "''")
        return Intent("SELECT l.name, f.subscribers FROM v_list_size f JOIN dim_list l USING (list_id) "
                      f"WHERE l.name = '{name}' ORDER BY f.snapshot_date DESC LIMIT 1",
                      f"abonnés de la liste « {named[0]} » à la dernière photo")
    if "liste" not in q:
        return None
    if has(q, r"perdu le plus", r"gagne le plus", r"plus perdu", r"plus gagne"):
        order = "ASC" if "perdu" in q else "DESC"
        return Intent("SELECT l.name, arg_max(f.subscribers, f.snapshot_date) - "
                      "arg_min(f.subscribers, f.snapshot_date) AS variation "
                      "FROM v_list_size f JOIN dim_list l USING (list_id) "
                      f"GROUP BY l.name ORDER BY variation {order} LIMIT 1",
                      f"liste qui a le plus {'perdu' if order == 'ASC' else 'gagné'} d'abonnés, première → dernière photo")
    if "abonne" in q and has(q, r"total", r"toutes les listes"):
        return Intent("SELECT SUM(subscribers) AS abonnes FROM v_list_size "
                      "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM v_list_size)",
                      "somme des abonnés de toutes les listes à la dernière photo "
                      "(un contact inscrit à plusieurs listes est compté plusieurs fois)")
    if has(q, r"combien", r"nombre") and "campagne" not in q:
        return Intent("SELECT COUNT(*) FROM dim_list", "nombre de listes de contacts")
    return None


def snapshot_date_intent(q: str) -> Intent | None:
    if "date" in q and has(q, r"derniere photo", r"dernier chargement", r"derniere mise a jour"):
        return Intent("SELECT MAX(snapshot_date) FROM fact_campaign_stats",
                      "date de la dernière photo des statistiques de campagne")
    return None


def change_intent(q: str, metric: Metric | None) -> Intent | None:
    if not has(q, r"supplementaire", r"entre la premiere et la derniere", r"\bvar(ie|iation)\b", r"evolu"):
        return None
    if not metric or metric.rate:
        return None
    col = metric.column.split(".")[1].replace("delivered", "delivered")
    return Intent(f"SELECT SUM(last) - SUM(first) AS variation FROM (SELECT arg_max({col}, snapshot_date) AS last, "
                  f"arg_min({col}, snapshot_date) AS first FROM fact_campaign_stats GROUP BY campaign_id)",
                  f"variation des {metric.label}, toutes campagnes, première → dernière photo")


COUNTABLE = {"desinscrit": "f.unsubscriptions", "clic": "f.clickers", "cliqueur": "f.clickers",
             "ouvreur": "f.unique_views", "ouverture": "f.unique_views", "plainte": "f.complaints",
             "hard bounce": "f.hard_bounces", "soft bounce": "f.soft_bounces"}
LABELS = {"f.unsubscriptions": "désinscrits", "f.clickers": "cliqueurs", "f.unique_views": "ouvreurs",
          "f.complaints": "plaintes", "f.hard_bounces": "hard bounces", "f.soft_bounces": "soft bounces"}


def _countable(word: str) -> str | None:
    for key, col in COUNTABLE.items():
        if word.startswith(key):
            return col
    return None


def comparison_intent(q: str) -> Intent | None:
    """'est-ce que les campagnes locales font plus de désinscrits que de clics ?'"""
    m = re.search(r"plus (?:de |d )(\w+(?: bounce)?) que (?:de |d |les |des )?(\w+(?: bounce)?)", q)
    if not m:
        return None
    a, b = _countable(m.group(1)), _countable(m.group(2))
    if not a or not b or a == b:
        raise NotUnderstood("Je n'ai pas reconnu les deux quantités à comparer.")
    parts: list[str] = []
    where, _ = campaign_filters(q.replace(m.group(0), " "), None, parts)
    count_only = has(q, r"combien de campagnes", r"nombre de campagnes") and not has(q, r"est.ce que")
    if count_only:
        select = "COUNT(*) FILTER (WHERE " + a + " > " + b + ") AS campagnes"
        label = f"nombre de campagnes avec plus de {LABELS[a]} que de {LABELS[b]}"
    else:
        select = (f"SUM({a}) AS {LABELS[a].replace(' ', '_')}, SUM({b}) AS {LABELS[b].replace(' ', '_')}, "
                  f"COUNT(*) FILTER (WHERE {a} > {b}) AS campagnes_concernees, COUNT(*) AS campagnes")
        label = f"comparaison {LABELS[a]} contre {LABELS[b]}"
        return Intent(BASE.format(select=select) + _where(where),
                      label + (" — " + ", ".join(parts) if parts else ""),
                      parts=[LABELS[a], LABELS[b]], kind="comparison")
    return Intent(BASE.format(select=select) + _where(where), label + (" — " + ", ".join(parts) if parts else ""))


# Rankings ignore tests and tiny sends, otherwise "worst campaigns" are always 0 % test emails.
RANKING_FLOOR = 1000
RANKING_FILTER = f"k.delivered >= {RANKING_FLOOR} AND lower(k.name) NOT LIKE 'test%'"


def campaigns_intent(q: str) -> Intent:
    metric = find_metric(q)
    parts: list[str] = []
    where, by_scope = campaign_filters(q, metric, parts)
    by_month = has(q, r"chaque mois", r"par mois", r"mois par mois")
    count_campaigns = has(q, r"combien de campagnes", r"nombre de campagnes")
    best = has(q, r"meilleur", r"plus eleve", r"le plus de", r"plus haut", r"\btop\b")
    worst = has(q, r"\bpire", r"plus faible", r"plus bas", r"le moins")
    is_avg = has(q, r"\bmoyen", r"moyenne")
    weighted = has(q, r"global", r"pondere", r"somme des")
    unit = " %" if metric and metric.rate else ""

    # superlative on months: "quel mois a le meilleur taux d'ouverture moyen ?"
    if (best or worst) and has(q, r"quel mois") and metric and metric.column:
        order = "DESC" if best else "ASC"
        sql = BASE.format(select=f"month(k.send_date) AS mois, ROUND(AVG({metric.column}), {metric.decimals}) AS valeur")
        sql += _where(where) + f" GROUP BY 1 ORDER BY AVG({metric.column}) {order} LIMIT 1"
        return Intent(sql, f"mois au {'meilleur' if best else 'plus faible'} {metric.label} moyen"
                      + (", " + ", ".join(parts) if parts else ""), unit)

    # superlative / top N on campaigns
    if (best or worst) and metric and metric.column and has(q, r"campagne", r"\bquel"):
        order = "DESC" if best else "ASC"
        n = find_n(q)
        sql = BASE.format(select=f"k.name, {metric.column} AS valeur")
        sql += _where(where + [RANKING_FILTER]) + f" ORDER BY {metric.column} {order}, k.name LIMIT {n}"
        what = f"{n} campagnes" if n > 1 else "campagne"
        if metric.rate:
            how = f"au {'meilleur' if best else 'plus faible'} {metric.label}"
        else:
            how = f"avec le {'plus' if best else 'moins'} de {metric.label}"
        parts.append(f"hors tests et envois de moins de {RANKING_FLOOR:,} e-mails".replace(",", " "))
        return Intent(sql, f"{what} {how}, " + ", ".join(parts), unit)

    # measures
    measures, labels = [], []
    if count_campaigns:
        measures.append("COUNT(*) AS campagnes")
        labels.append("nombre de campagnes")
    if metric and not (count_campaigns and metric.key == "unsubscriptions" and "que de cliqueurs" in q):
        if metric.rate and (weighted or not metric.column):
            measures.append(f"ROUND(100.0 * SUM({metric.num}) / NULLIF(SUM({metric.den}), 0), {metric.decimals}) AS valeur")
            labels.append(f"{metric.label} global (pondéré)")
        elif metric.rate and (is_avg or not count_campaigns):
            measures.append(f"ROUND(AVG({metric.column}), {metric.decimals}) AS valeur")
            labels.append(f"{metric.label} moyen")
        elif not metric.rate and is_avg:
            decimals = 0 if has(q, r"unite", r"entier") else 2
            measures.append(f"ROUND(AVG({metric.column}), {decimals}) AS valeur")
            labels.append(f"{metric.label} en moyenne par campagne")
        elif not metric.rate and not (count_campaigns and not has(q, r"total", r"somme", r"\bet\b")):
            measures.append(f"SUM({metric.column}) AS valeur")
            labels.append(f"total des {metric.label}")
    if not measures:
        if count_campaigns or has(q, r"combien", r"nombre"):
            measures.append("COUNT(*) AS campagnes")
            labels.append("nombre de campagnes")
        else:
            raise NotUnderstood("Je n'ai pas reconnu ce qu'il faut calculer.")

    groups = []
    if by_scope:
        groups.append("k.scope")
        parts.append("par périmètre")
    if by_month:
        groups.append("month(k.send_date)")
        parts.append("par mois")
    select = ", ".join([g.replace("month(k.send_date)", "month(k.send_date) AS mois") for g in groups] + measures)
    sql = BASE.format(select=select) + _where(where)
    if groups:
        sql += " GROUP BY " + ", ".join(groups) + " ORDER BY " + ", ".join(groups)
    if not metric or not metric.rate or count_campaigns and len(measures) == 1:
        unit = ""
    return Intent(sql, ", ".join(labels) + (" — " + ", ".join(parts) if parts else ""), unit)


def parse(question: str, list_names: list[str] | None = None) -> Intent:
    q = normalise(question)
    if not q:
        raise NotUnderstood("Question vide.")
    if has(q, r"^(supprime|efface|modifie|change|cree|ajoute|envoie|mets?|renomme|vide|ecris|redige|genere)"):
        raise NotUnderstood("L'assistant lit les données, il ne modifie rien.")
    for attempt in (lambda: snapshot_date_intent(q), lambda: lists_intent(q, list_names or [])):
        intent = attempt()
        if intent:
            return intent
    if has(q, r"\bjour de la semaine\b", r"\bheure\b", r"chiffre d affaire", r"\bpoints?\b", r"\bclient"):
        raise NotUnderstood("Ces données ne sont pas dans l'entrepôt (jours, heures, ventes, clients).")
    if not has(q, r"campagne", r"email", r"envoi", r"taux", r"ctor", r"delivre", r"cliqueur",
               r"ouvreur", r"desinscri", r"bounce", r"plainte", r"spam", r"perimetre", r"\bmois\b"):
        raise NotUnderstood("Cette question ne porte pas sur les campagnes ni sur les listes de contacts.")
    intent = comparison_intent(q)
    if intent:
        return intent
    if has(q, r"^est.ce que", r"\best.ce qu"):
        raise NotUnderstood("Je ne sais pas encore répondre par oui ou non à ce type de question.")
    metric = find_metric(q)
    intent = change_intent(q, metric)
    return intent or campaigns_intent(q)
