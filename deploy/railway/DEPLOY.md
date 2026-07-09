# Railway Deployment Guide

## What you get

| Property | Value |
|----------|-------|
| Cost | $5/month (Hobby plan) or free with usage limits |
| Deploy method | Git push → automatic build & deploy |
| Model strategy | Baked into Docker image at build time |
| Custom domain | Yes (included) |
| TLS | Automatic |
| Cold starts | None (always-on on Hobby plan) |
| Deploy time | ~8 min first deploy (trains model), ~2 min after (cached) |

## Prerequisites

```bash
# Install Railway CLI
npm install -g @railway/cli

# Or with brew
brew install railway
```

## Step 1 — Login and create project

```bash
railway login

# Create a new project from the repo root
railway init

# When prompted:
#   Project name: phishguard
#   Confirm: yes
```

## Step 2 — Set environment variables

```bash
# Generate a secure secret key
SECRET_KEY=$(python scripts/generate_secret_key.py)

# Set all required variables
railway variables set SECRET_KEY="$SECRET_KEY"
railway variables set MODEL_PATH="/app/models/phishing_model.joblib"
railway variables set WEB_CONCURRENCY="2"
railway variables set LOG_LEVEL="info"
railway variables set PORT="5000"

# Verify
railway variables
```

## Step 3 — Link the Railway config

```bash
# Copy railway.json to project root (Railway looks for it there)
cp deploy/railway/railway.json railway.json

# Add to git
git add railway.json
git commit -m "deploy: add Railway configuration"
```

## Step 4 — Deploy

```bash
# First deploy (triggers build + training — takes ~8 minutes)
railway up

# Watch the build logs
railway logs --build

# Watch the runtime logs
railway logs
```

## Step 5 — Verify

```bash
# Get your deployment URL
railway status

# Health check
curl https://your-app.railway.app/api/health

# Test a prediction
curl -X POST https://your-app.railway.app/api/predict \
  -H "Content-Type: application/json" \
  -d '{"url": "http://paypal-secure.tk/verify/login"}'
```

## Step 6 — Custom domain (optional)

```bash
# In Railway dashboard: Settings → Domains → Add Custom Domain
# Then add a CNAME record at your DNS provider:
#   CNAME phishguard.yourdomain.com → your-app.up.railway.app
```

## Automatic deploys from GitHub

After linking Railway to your GitHub repo
(Railway Dashboard → Settings → Connect GitHub):

Every push to `main` triggers a new build and deploy automatically.

## Cost breakdown

| Plan | Price | RAM | CPU | Bandwidth |
|------|-------|-----|-----|-----------|
| Free (Trial) | $0 (500 hours/mo) | 512 MB | Shared | 100 GB |
| Hobby | $5/month | 512 MB | Shared | 100 GB |
| Pro | $20/month | 8 GB | 8 vCPU | Unlimited |

**Recommended:** Hobby ($5/mo) — no cold starts, always available for recruiters.

## Troubleshooting

**Build fails during training:**
```bash
# Check build logs
railway logs --build

# The --cap 10000 flag in Dockerfile.railway limits training data.
# If Railway times out (15 min limit), reduce the cap:
# Edit deploy/railway/Dockerfile.railway: --cap 5000
```

**`status: degraded` on /api/health:**
```bash
# The model path env var may be wrong
railway variables set MODEL_PATH="/app/models/phishing_model.joblib"
railway redeploy
```

**Port not binding:**
```bash
# Railway injects PORT automatically — gunicorn.conf.py reads it
# Verify: railway variables | grep PORT
```
