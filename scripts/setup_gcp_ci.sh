#!/usr/bin/env bash
# One-time setup, to paste in Google Cloud Shell (the terminal icon at the top of the console).
# Lets GitHub Actions use BigQuery WITHOUT any key: GitHub proves who it is to Google, and
# Google only accepts runs coming from this one repository.
set -euo pipefail

REPO="thibaultbordrie-cloud/brevo-campaign-warehouse"
PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
SA_NAME="brevo-ci"
SA="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
echo "Project: $PROJECT_ID ($PROJECT_NUMBER)"

# 1. Services needed (all free)
gcloud services enable bigquery.googleapis.com iam.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com

# 2. A robot account for the CI, allowed to write tables and run queries, nothing else
gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
  gcloud iam service-accounts create "$SA_NAME" --display-name="brevo-warehouse CI (no key)"
for ROLE in roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" \
    --role="$ROLE" --condition=None >/dev/null
done

# 3. Trust GitHub's identity tokens, but only for this repository
gcloud iam workload-identity-pools describe github --location=global >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers describe brevo-warehouse --location=global \
  --workload-identity-pool=github >/dev/null 2>&1 || \
  gcloud iam workload-identity-pools providers create-oidc brevo-warehouse \
    --location=global --workload-identity-pool=github \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='$REPO'"

# 4. Runs of that repository may act as the robot account
gcloud iam service-accounts add-iam-policy-binding "$SA" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO" \
  >/dev/null

echo
echo "Done. Create these 3 VARIABLES in GitHub (Settings > Secrets and variables > Actions > Variables):"
echo "  GCP_PROJECT_ID       = $PROJECT_ID"
echo "  GCP_WIF_PROVIDER     = projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/brevo-warehouse"
echo "  GCP_SERVICE_ACCOUNT  = $SA"
echo "None of them is a secret: without a run from $REPO, they open nothing."
