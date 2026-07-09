# PhishGuard — Free Deployment Guide

## Platform Comparison (verified June 2026)

| | Render | GCP Cloud Run |
|---|---|---|
| **Cost** | $0 (750 hrs/month) | $0 (2M req/month) |
| **Credit card** | No | Yes (not charged) |
| **Always-on** | No (spins down after 15 min) | No (scales to zero) |
| **Cold start** | 30–60 seconds | 2–8 seconds |
| **RAM** | 512 MB | 512 MB |
| **CPU** | Shared | 1 vCPU (during request) |
| **Deploy method** | Git push via Blueprint | GitHub Actions → Artifact Registry |
| **Auto-deploy** | Yes (push to main) | Yes (via workflow) |
| **Custom domain** | Yes (free) | Yes (free) |
| **TLS** | Automatic | Automatic |
| **Model strategy** | Baked into image | Baked into image |
| **Best for** | Portfolio demos, no card setup | Production-quality showcase |

### Which should you use?

**Use Render if:** you want the fastest possible setup with zero friction.
No card, no GCP project, no CLI. Push code, get URL. Done.

**Use GCP Cloud Run if:** you want the most impressive portfolio entry.
Cloud Run is what production ML APIs actually run on. Interviewers notice
the difference between "deployed on Render" and "deployed on Cloud Run
with Workload Identity Federation and Artifact Registry."

**Use both:** Render for the live demo link in your README, Cloud Run for
the architecture section. They use the same Docker image.

---

## Option A: Render (Fastest — No Card Required)

### Prerequisites
- GitHub account with this repo pushed
- Render account at render.com (email signup, no card)

### Step 1 — Prepare the Blueprint file

```bash
# Copy render.yaml to the repo root (Render looks there by default)
cp deploy/render/render.yaml render.yaml
git add render.yaml
git commit -m "deploy: add Render Blueprint"
git push origin main
```

### Step 2 — Create the service

1. Go to **dashboard.render.com**
2. Click **New → Blueprint**
3. Connect your GitHub repo when prompted
4. Render reads `render.yaml` and shows you the service to create
5. Click **Apply** — the first build starts immediately

> **Build time:** ~12 minutes (training Random Forest with 8,000 URLs per class).
> Subsequent deploys use Docker layer cache — ~3 minutes.

### Step 3 — Verify

```bash
# Replace with your actual Render URL
export URL=https://phishguard.onrender.com

curl $URL/api/health

# Expected:
# {"model_loaded": true, "num_features": 28, "status": "ok"}
```

```bash
# Test a phishing URL
curl -X POST $URL/api/predict \
  -H "Content-Type: application/json" \
  -d '{"url": "http://paypal-verify.account-secure.tk/login"}'
```

### Step 4 — Enable keep-alive (prevents 30–60s cold start)

```bash
# Add your Render URL as a GitHub secret
# Settings → Secrets → New secret
# Name:  RENDER_URL
# Value: https://phishguard.onrender.com
```

The `.github/workflows/keep-alive.yml` pings `/api/health` every 14 minutes
automatically — your service stays warm and responds instantly.

### Step 5 — Custom domain (optional, free)

1. Render Dashboard → your service → **Settings → Custom Domains**
2. Add `phishguard.yourdomain.com`
3. At your DNS provider, add a CNAME:
   ```
   phishguard  CNAME  phishguard.onrender.com
   ```

---

## Option B: GCP Cloud Run ($0/month with card on file)

### Free tier limits that matter
- **2,000,000 requests/month** — your entire portfolio lifetime of traffic
- **180,000 vCPU-seconds/month** — ~50 hours of active compute
- **360,000 GB-seconds/month** — ~100 hours at 512 MB RAM
- **1 GB egress/month** — sufficient for demo traffic
- **Region:** must be `us-central1`, `us-east1`, or `us-west1`

### Prerequisites

```bash
# Install gcloud CLI
# macOS
brew install --cask google-cloud-sdk

# Linux
curl https://sdk.cloud.google.com | bash
exec -l $SHELL

# Windows: https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud auth application-default login
```

### Step 1 — Create a GCP project

```bash
# Option A: via CLI
gcloud projects create phishguard-demo-$(date +%Y%m) --name="PhishGuard"
export GCP_PROJECT_ID=phishguard-demo-$(date +%Y%m)
gcloud config set project $GCP_PROJECT_ID

# Option B: via Console
# console.cloud.google.com → New Project
```

> **Billing:** Go to console.cloud.google.com/billing and link a billing account.
> You will NOT be charged — Cloud Run in us-central1 stays within free tier
> at portfolio traffic levels. Billing must be enabled to use the API.

### Step 2 — Run the one-time setup

```bash
export GCP_PROJECT_ID=your-project-id
export GITHUB_USERNAME=rahulkp-ai
export GITHUB_REPO=phishing-detection

# Enables APIs, creates Artifact Registry, stores SECRET_KEY in Secret Manager
bash deploy/gcp/setup.sh
```

This takes ~3 minutes. It enables the Cloud Run, Cloud Build, Artifact
Registry, and Secret Manager APIs, creates the image repository, and stores
your `SECRET_KEY` in Secret Manager (encrypted, never in code or env files).

### Step 3 — Set up Workload Identity Federation

```bash
# Creates WIF pool + provider — no long-lived keys stored anywhere
bash deploy/gcp/setup-wif.sh
```

Copy the three output values and add them as GitHub Secrets:
- `GCP_PROJECT_ID`
- `GCP_WORKLOAD_IDENTITY`
- `GCP_SERVICE_ACCOUNT`

### Step 4 — Push to main to trigger deploy

```bash
git add deploy/gcp/ .github/workflows/deploy-gcp.yml
git commit -m "deploy: add GCP Cloud Run deployment"
git push origin main
```

Watch the deploy in the Actions tab. First run: ~12 minutes. Subsequent
runs with layer cache: ~4 minutes.

### Step 5 — Get your URL

```bash
gcloud run services describe phishguard \
  --region=us-central1 \
  --format='value(status.url)'

# Output: https://phishguard-xxxx-uc.a.run.app
```

### Step 6 — Verify

```bash
export URL=$(gcloud run services describe phishguard \
  --region=us-central1 --format='value(status.url)')

# Health check
curl $URL/api/health

# Prediction
curl -X POST $URL/api/predict \
  -H "Content-Type: application/json" \
  -d '{"url": "http://paypal-verify.account-secure.tk/login"}'

# Batch
curl -X POST $URL/api/batch \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://google.com", "http://evil-phish.tk/login"]}'
```

### Step 7 — Custom domain (optional, free)

```bash
# Map your domain to Cloud Run
gcloud beta run domain-mappings create \
  --service=phishguard \
  --domain=phishguard.yourdomain.com \
  --region=us-central1

# Add the CNAME shown in the output to your DNS provider
```

---

## Monitoring your free tier usage

```bash
# Cloud Run: requests this month
gcloud logging read \
  'resource.type="cloud_run_revision" resource.labels.service_name="phishguard"' \
  --limit=10 \
  --format='table(timestamp, httpRequest.requestUrl, httpRequest.status)'

# Check current billing (should be $0.00)
open https://console.cloud.google.com/billing
```

---

## README badges to add after deployment

```markdown
<!-- Replace URLs with your actual deployment URLs -->

![Render](https://img.shields.io/badge/Render-Live_Demo-46E3B7?logo=render)
![Cloud Run](https://img.shields.io/badge/Cloud_Run-Deployed-4285F4?logo=googlecloud)
[![Health](https://img.shields.io/website?url=https%3A%2F%2Fphishguard.onrender.com%2Fapi%2Fhealth&label=API)](https://phishguard.onrender.com/api/health)
```

---

## Cost guarantee

At portfolio traffic (< 10,000 requests/month):

| Platform | Monthly cost |
|----------|-------------|
| Render | **$0.00** |
| GCP Cloud Run | **$0.00** |
| GCP Artifact Registry | **$0.00** (< 0.5 GB) |
| GCP Secret Manager | **$0.00** (< 6 versions) |
| GitHub Actions | **$0.00** (public repo) |
| **Total** | **$0.00** |
