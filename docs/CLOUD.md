# Cloud copy on BigQuery

The same warehouse and the same dbt models, running on Google BigQuery instead of DuckDB.

## What runs where

```
GitHub Actions (on every push to main)
  1. signs in to Google with no stored key (Workload Identity Federation)
  2. scripts/load_to_bigquery.py   builds the FICTIONAL demo warehouse and loads
                                   4 tables into the dataset brevo_raw (Parquet load jobs)
  3. dbt build --target bigquery   creates brevo_staging, brevo_intermediate, brevo_marts
                                   and runs the 28 data tests there
```

The dbt models are written in portable SQL (`strpos`, `dbt.date_trunc`, `qualify` after a `where`),
so one code base serves both engines. The source dataset switches on `target.type`.

## Security

- **Fictional data only.** The loader builds its own demo warehouse and has no way to read the real
  one; a test checks it. Company data stays on the company computer.
- **No key anywhere.** GitHub sends a short-lived identity token; Google accepts it only for runs of
  `thibaultbordrie-cloud/brevo-campaign-warehouse` (attribute condition), and maps it to a service account
  that can only write BigQuery tables and run queries.
- The three GitHub variables (`GCP_PROJECT_ID`, `GCP_WIF_PROVIDER`, `GCP_SERVICE_ACCOUNT`) are not
  secrets: they open nothing outside a run of this repository.

## Costs

| Item | In the sandbox |
|---|---|
| Billing account | none: nothing can be charged |
| Storage | 10 GB free (this project: well under 1 MB) |
| Queries | 1 TB read per month free (one CI run reads a few MB) |
| Load jobs | always free |
| Tables | expire after 60 days (rebuilt by every run) |

Guards in place even so:

- `maximum_bytes_billed: 1000000000` in `transform/profiles.yml`: BigQuery refuses any dbt query
  that would read more than 1 GB, before running it.
- Marts are tables, staging and intermediate are views: the views cost nothing to store.

A **budget alert** needs a billing account, which the sandbox does not have. If billing is ever
enabled: Billing > Budgets & alerts > Create budget, amount 1 EUR, alerts at 50 %, 90 % and 100 %
of actual spend, emailed to the billing administrator. Note that a budget only warns: it does not
stop spending; the byte cap above is what actually blocks an expensive query.

## Setup (once)

1. Open the BigQuery sandbox (https://console.cloud.google.com/bigquery) with a personal Google
   account and create a project. No credit card.
2. Open Cloud Shell, upload `scripts/setup_gcp_ci.sh` and run `bash setup_gcp_ci.sh`.
3. Copy the three values it prints into GitHub: Settings > Secrets and variables > Actions >
   Variables. The `bigquery` job of the CI starts on the next push.
