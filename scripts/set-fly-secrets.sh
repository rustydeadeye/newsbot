#!/usr/bin/env bash
# Set all production secrets on Fly.io for the financeai app.
# Fill in the values below, then run: bash scripts/set-fly-secrets.sh
# DO NOT commit this file after filling in real values.

set -euo pipefail

APP="financeai"

fly secrets set --app "$APP" \
  DATABASE_URL="postgresql+psycopg://postgres.<ref>:<password>@db.<ref>.supabase.co:5432/postgres" \
  SUPABASE_URL="https://<ref>.supabase.co" \
  SUPABASE_PUBLISHABLE_KEY="<your-supabase-anon-key>" \
  SUPABASE_JWT_SECRET="<your-supabase-jwt-secret>" \
  OPENAI_API_KEY="<your-openai-api-key>" \
  X_CLIENT_ID="<your-x-client-id>" \
  X_CLIENT_SECRET="<your-x-client-secret>" \
  AUTH_ADMIN_EMAILS="" \
  AUTH_AUTO_PROVISION_USERS="true" \
  FRONTEND_URL="https://<your-netlify-site>.netlify.app" \
  CORS_ORIGINS='["https://<your-netlify-site>.netlify.app"]'

echo "Secrets set on $APP."
