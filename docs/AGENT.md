# Question assistant

Ask a question in French about the campaigns or the contact lists; the assistant builds one
SQL query, runs it on the warehouse **read-only**, and answers in one sentence, saying what it
understood and showing the query.

```
run.bat ask "Combien de campagnes locales en mars 2026 ?"
  Nombre de campagnes — périmètre local, mars 2026 : 4.
run.bat eval          score on the test questions, report saved in reports/
```

## Why rules and not an AI model

The work computer cannot install a model, no paid API is allowed, and no key may be stored.
So the assistant uses **rules only**: free, offline, instant, and it runs where the data is.
The trade-off is coverage: it only understands the kinds of questions its rules describe. In
exchange, it **never guesses**: a question it does not recognise gets "je ne sais pas" and
example questions, which an AI model rarely does.

## How a question is read (`agent/parser.py`)

1. **Normalise**: lower case, no accents, "nb" → "nombre", "e-mail" → "email".
2. **Refuse** early: actions (supprime, modifie, envoie, écris...), and data the warehouse does
   not hold (customers, points, sales, days, hours).
3. **Subject**: last snapshot date, contact lists, change between first and last snapshot,
   otherwise campaigns.
4. **Measure**, first match in a fixed order (rates before raw counts): open rate, click rate,
   CTOR, unsubscribe rate, soft / hard bounce rate, complaints, bounces, unsubscriptions,
   clickers, openers, deliveries.
5. **Calculation**: count, total, average, global (weighted) rate, best / worst / top N, month
   with the best average.
6. **Filters and groups**: local / national, a month, a half-year, a year, a threshold
   ("supérieur à 15 %"), store closures, "plus de désinscrits que de cliqueurs"; per scope, per
   month.

Every value placed in the SQL comes from a fixed list or from a list name that exists in the
database: the text typed by the user is never pasted into a query (a test tries an injection).

## Router

The router decides between two paths: **recognised** → SQL built by the rules, checked by the
guard, run; **not recognised** → honest refusal with examples. A third path (a local model on a
personal computer for unrecognised questions) is left out on purpose: it is the natural next
step outside work, and the guard below would apply to it unchanged.

## Guard rails (each one is enough on its own)

| Lock | What it stops |
|---|---|
| DuckDB opened `read_only=True` | any write |
| `enable_external_access = false` | reading files (`read_csv('C:/...')`), `ATTACH`, network |
| Text check: one statement, `SELECT`/`WITH` only, forbidden words and functions | `DROP`, `COPY`, `PRAGMA`, `getenv()`, several statements |
| `LIMIT 200` wrapped around every query | dumping whole tables |
| 15 s timeout (`con.interrupt()`) | runaway queries |

The rules only build safe queries, but every query still goes through the guard: defence in
depth. Tests attack each lock.

## Evaluation (always on fictional data)

| Set | Questions | Score |
|---|---|---|
| `evals/questions.json`, written together with the rules | 15 simple + 15 complex | 30/30 |
| `evals/questions_variants.json`, paraphrases written **after** the rules | 20 | 18/20 at the first run, 20/20 after two fixes ("nb", a list named without the word "liste") |
| Out-of-scope questions, which must be refused | 6 | 6/6 |

| First test by a user (8 questions typed freely) | 8 | 5 right, 1 right but badly worded, **2 wrong**, all fixed and kept as v21-v23 |

What that test found: a yes / no comparison ("est-ce que les locales font plus de désinscrits
que de clics ?") was answered with a single total, which is the worst kind of error (a confident
wrong answer); "les 5 pires campagnes" only listed 0 % test emails; the total of subscribers came
out as 0 (now shown with unique subscribers next to it). Since then: comparisons get a yes / no
sentence with both totals, other yes / no questions are refused, rankings ignore tests and sends
under 1,000 e-mails, months are written in words.

The first set says little on its own (same author as the rules); the variants measure how far
the rules generalise, and their **first** score (90 %) is the honest number. All three scores
are CI tests: a change that breaks a question that used to work turns CI red.

## Known limits

- Only the question shapes above. "Quel jour de la semaine...", "la semaine dernière", "les
  campagnes de Noël" (no tag for it) are refused, not guessed.
- "Le mois dernier", "cette année" are not understood: dates must be explicit (mars 2026).
- Paraphrases written by other people will score lower than 90 %: each miss is a rule to add,
  and a test question to keep.
- Two measures in one question are only supported for "nombre de campagnes et total de ...".
