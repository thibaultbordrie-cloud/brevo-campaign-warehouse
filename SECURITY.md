# Security

## What this repository contains

Code, tests and **fictional** data only. No API key, no password, no customer data and no
business figure is stored here, and tests enforce it:

- `tests/test_vault.py` scans every tracked file for Brevo key patterns;
- `tests/test_anonymity.py` refuses identifying names (kept as hashes), non-example e-mail
  addresses and public IP addresses.

## How secrets are handled

- Local runs read keys from the Windows Credential Manager (`python run.py secret set ...`),
  never from a file in the project.
- CI signs in to Google Cloud with Workload Identity Federation: no key is stored in GitHub.
- Workflows run with a read-only token unless a job needs more (Pages, BigQuery).
- Dependabot proposes updates of actions and Python dependencies every week.

## Reporting a problem

If you find something sensitive in this repository, please open a
[private security advisory](../../security/advisories/new) rather than a public issue.
