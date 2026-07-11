---
title: PhishGuard
emoji: 🛡️
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# PhishGuard — Phishing URL Detection API

ML-powered phishing URL detection using Random Forest + 28 hand-engineered features.

## API

**POST** `/api/predict`

```json
{ "url": "https://example.com" }
```

**GET** `/api/health`

# PhishGuard 🛡️

**ML-powered phishing URL detection — production-grade MLOps portfolio project**

**Built by [Rahul K P](https://github.com/rahulkp-ai) — ML Engineer · GenAI · MSc CS 2026**

[![CI](https://github.com/rahulkp-ai/phishguard/actions/workflows/ci.yml/badge.svg)](https://github.com/rahulkp-ai/phishguard/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/rahulkp-ai/phishguard/branch/main/graph/badge.svg)](https://codecov.io/gh/rahulkp-ai/phishguard)
[![Python](https://img.shields.io/badge/python-3.10%20|%203.12-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask)](https://flask.palletsprojects.com/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?style=flat-square&logo=docker&logoColor=white)](./docker/)
[![Kubernetes](https://img.shields.io/badge/Kubernetes-manifests-326CE5?style=flat-square&logo=kubernetes&logoColor=white)](./k8s/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](./LICENSE)

[![LinkedIn](https://img.shields.io/badge/LinkedIn-rahulkp--ai-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/rahulkp-ai/)
[![Kaggle](https://img.shields.io/badge/Kaggle-rahulkpai-20BEFF?style=flat-square&logo=kaggle&logoColor=white)](https://www.kaggle.com/rahulkpai)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0009--3403--6670-A6CE39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0009-3403-6670)

---

## What is PhishGuard?

PhishGuard is a **production-grade MLOps project** that detects phishing URLs in real time using a Random Forest classifier trained on 28 hand-engineered URL features. It goes beyond a typical ML project by implementing the full engineering stack a real ML product needs: a REST API, containerized deployment, CI/CD pipelines, Kubernetes manifests, and a Prometheus/Grafana observability layer with prediction drift detection.

**This project is intentionally over-engineered** — every layer (logging, metrics, drift detection, K8s security contexts, WIF auth) is there to demonstrate production engineering judgment, not because a portfolio demo needs it.

---

## Model Performance

| Metric               | Score |
| -------------------- | ----- |
| Accuracy             | ~95%  |
| ROC-AUC              | ~0.98 |
| Precision (Phishing) | ~94%  |
| Recall (Phishing)    | ~96%  |
| F1 (Phishing)        | ~95%  |

Trained on ~50,000 balanced URLs from OpenPhish, URLhaus, PhishTank, Majestic Million, and Tranco.

---

## Architecture

```
                        ┌─────────────────────────────────┐
                        │         GitHub Actions CI        │
                        │  lint → test → coverage → build  │
                        └──────────────┬──────────────────┘
                                       │ push to main
                                       ▼
┌──────────────┐    POST /api/predict  ┌─────────────────┐    joblib.load()   ┌──────────────┐
│   Client /   │ ────────────────────► │   Flask API     │ ──────────────────► │ Random Forest│
│   Web UI     │ ◄──────────────────── │  (gunicorn)     │ ◄────── predict()── │  Classifier  │
└──────────────┘    JSON response      └────────┬────────┘                    └──────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
           ┌──────────────┐          ┌─────────────────┐         ┌──────────────────┐
           │  structlog   │          │   Prometheus     │         │  DriftDetector   │
           │  JSON logs   │          │   /metrics       │         │  rolling window  │
           │  + request ID│          │   scrape target  │         │  phishing rate   │
           └──────────────┘          └────────┬────────┘         └──────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │     Grafana      │
                                    │  9-panel dashboard│
                                    │  + alert rules   │
                                    └─────────────────┘
```

---

## Key Engineering Decisions

| Decision            | Choice                              | Why                                              |
| ------------------- | ----------------------------------- | ------------------------------------------------ |
| Package layout      | `src/` layout                       | Prevents accidental imports from repo root       |
| Model serialization | `joblib`                            | Safer and faster than `pickle` for sklearn       |
| Logging             | `structlog` + stdlib bridge         | JSON in prod, coloured in dev, quiet in tests    |
| Secret management   | Env vars + Secret Manager           | Never in code, never in `.env.example`           |
| Container security  | Non-root uid=1001, read-only rootfs | Defence in depth                                 |
| CI auth to GCP      | Workload Identity Federation        | No long-lived service account keys               |
| Metric cardinality  | Blueprint-prefixed endpoint names   | Prevents label explosion from variable URL paths |

---

## Tech Stack

**ML & Data:** scikit-learn · pandas · numpy · joblib

**API:** Flask 3 · gunicorn · structlog · prometheus-client

**Testing:** pytest · pytest-cov · 222 tests · 98%+ coverage

**DevOps:** Docker · Docker Compose · GitHub Actions · Kustomize · Kubernetes

**Observability:** Prometheus · Grafana · prediction drift detection

**Cloud:** GCP Cloud Run · Render · Artifact Registry · Secret Manager

---

## Project Structure

```
phishguard/
├── src/phishguard/              # installable package (pip install -e .)
│   ├── features/extractor.py    # 28 URL features, zero side effects on import
│   ├── data/
│   │   ├── downloader.py        # multi-source URL feed downloader
│   │   └── builder.py           # feature extraction → balanced CSV dataset
│   ├── models/trainer.py        # Random Forest training, joblib serialization
│   ├── logging_config.py        # structlog + stdlib unified config
│   ├── metrics.py               # all Prometheus metric definitions
│   └── drift.py                 # rolling-window prediction drift detector
│
├── app/                         # Flask application
│   ├── __init__.py              # app factory
│   ├── config.py                # Dev/Prod/Testing config classes
│   ├── routes.py                # /api/predict, /api/batch, /api/health, /metrics
│   ├── middleware.py            # request ID + structured request logging
│   ├── metrics_middleware.py    # Prometheus HTTP instrumentation
│   └── templates/               # web UI
│
├── tests/                       # 222 tests, 98%+ coverage
│   ├── conftest.py              # shared fixtures, --fast flag
│   ├── test_features.py         # URL scoring behaviour tests
│   ├── test_extractor_coverage.py  # graded threshold branch coverage
│   ├── test_routes.py           # API endpoint tests
│   ├── test_routes_coverage.py  # 503/500/validation edge cases
│   ├── test_integration_*.py    # real file I/O, no network
│   ├── test_downloader.py       # mocked HTTP, logging regression tests
│   ├── test_metrics.py          # Prometheus + drift detector unit tests
│   ├── test_logging.py          # request ID middleware tests
│   └── test_config.py           # config validation tests
│
├── docker/                      # Dockerfile, gunicorn config, compose files
├── k8s/                         # Kubernetes base + dev/staging/prod overlays
├── deploy/                      # Render and GCP Cloud Run configs + guide
├── monitoring/                  # Prometheus, Grafana dashboard, alert rules
├── scripts/                     # train_pipeline.py, generate_secret_key.py
└── .github/workflows/           # CI, CodeQL, docker-publish, release, deploy
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- `pip`

### 1. Install

```bash
git clone https://github.com/rahulkp-ai/phishguard.git
cd phishguard
pip install -e ".[dev]"
```

### 2. Train the model

```bash
python scripts/train_pipeline.py
```

This downloads phishing and legitimate URL feeds, extracts 28 features per URL, and trains the Random Forest. Takes ~8–12 minutes on the first run. Use `--cap 5000` to limit dataset size for a quick test:

```bash
python scripts/train_pipeline.py --cap 5000
```

If you already have URL files in `data/processed/`:

```bash
python scripts/train_pipeline.py --skip-download
```

### 3. Run

```bash
# Set a secret key (required)
export SECRET_KEY=$(python scripts/generate_secret_key.py)

# Start the dev server
python run.py
```

Open `http://localhost:5000` in your browser.

### 4. Test a prediction

```bash
curl -X POST http://localhost:5000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"url": "http://paypal-verify-secure.account.tk/login"}'
```

```json
{
  "url": "http://paypal-verify-secure.account.tk/login",
  "is_phishing": true,
  "label": "PHISHING",
  "phishing_pct": 97.4,
  "legit_pct": 2.6,
  "confidence": 97.4,
  "risk_level": "HIGH",
  "analysis_time_ms": 6.2
}
```

---

## API Reference

### `GET /api/health`

```json
{
  "status": "ok",
  "model_loaded": true,
  "num_features": 28
}
```

Returns `"degraded"` if the model isn't loaded — pod stays in the load balancer but predictions return 503.

### `POST /api/predict`

```json
{ "url": "https://example.com" }
```

| Field              | Type   | Description                                  |
| ------------------ | ------ | -------------------------------------------- |
| `is_phishing`      | bool   | Model classification                         |
| `label`            | string | `"PHISHING"` or `"LEGITIMATE"`               |
| `phishing_pct`     | float  | Phishing probability 0–100                   |
| `confidence`       | float  | Max class probability 0–100                  |
| `risk_level`       | string | `HIGH` / `MEDIUM` / `LOW` / `SAFE`           |
| `features`         | object | 10 key feature values used in classification |
| `analysis_time_ms` | float  | End-to-end latency in milliseconds           |

### `POST /api/batch`

```json
{ "urls": ["https://google.com", "http://evil.tk/login"] }
```

Up to 50 URLs per request. Each URL is analysed independently — one invalid URL doesn't fail the batch.

### `GET /metrics`

Prometheus text exposition format. Key metrics:

| Metric                                     | Type      | Description                 |
| ------------------------------------------ | --------- | --------------------------- |
| `phishguard_http_requests_total`           | Counter   | By method, endpoint, status |
| `phishguard_http_request_duration_seconds` | Histogram | p50/p95/p99 latency         |
| `phishguard_predictions_total`             | Counter   | By label, risk level        |
| `phishguard_prediction_confidence`         | Histogram | Confidence distribution     |
| `phishguard_phishing_rate_1m`              | Gauge     | Rolling phishing rate       |
| `phishguard_drift_detected`                | Gauge     | 1 when drift is active      |

---

## Running Tests

```bash
# Fast feedback (unit tests only, ~0.7s)
pytest tests/ --fast

# Full suite including integration tests (~11s)
pytest tests/

# With coverage report
pytest tests/ --cov --cov-report=term-missing

# Integration tests only
pytest tests/ -m integration
```

---

## Docker

```bash
# Build
make docker-build

# Train model (writes to named volume)
make docker-train

# Run
make docker-run SECRET_KEY=$(python scripts/generate_secret_key.py)

# Full monitoring stack (PhishGuard + Prometheus + Grafana)
docker compose -f monitoring/docker-compose.monitoring.yml up
```

Grafana dashboard auto-provisions at `http://localhost:3000` (admin/admin).

---

## Kubernetes

```bash
# Replace the image placeholder
find k8s/ -name "*.yaml" -exec sed -i 's/YOUR_GITHUB_USERNAME/rahulkp-ai/g' {} +

# Deploy to local minikube
minikube start --cpus=2 --memory=4096
minikube addons enable metrics-server
kubectl apply -k k8s/overlays/dev

# Create the secret
export SECRET_KEY=$(python scripts/generate_secret_key.py)
bash k8s/scripts/create-secrets.sh

# Access
kubectl port-forward svc/phishguard 5000:80 -n phishguard
```

Three overlays available: `dev` (1 replica, minikube), `staging` (2 replicas, Let's Encrypt staging TLS), `production` (3 replicas, HA, prod TLS, RWX storage).

---

## Cloud Deployment (Free Tier)

See [`deploy/DEPLOYMENT_GUIDE.md`](./deploy/DEPLOYMENT_GUIDE.md) for full step-by-step instructions.

| Platform          | Cost     | Setup time | Notes                                                                                     |
| ----------------- | -------- | ---------- | ----------------------------------------------------------------------------------------- |
| **Render**        | $0/month | ~5 min     | No card. Spins down after 15 min idle. Keep-alive workflow included.                      |
| **GCP Cloud Run** | $0/month | ~20 min    | Card required (not charged at portfolio scale). 2M requests/month free. us-central1 only. |

The model is baked into the Docker image at build time, working around free-tier stateless container limits.

---

## CI/CD Pipelines

| Workflow                | Trigger                 | What it does                                                                          |
| ----------------------- | ----------------------- | ------------------------------------------------------------------------------------- |
| `ci.yml`                | Push / PR to main       | Lint → unit tests (py3.10 + py3.12) → full tests + coverage gate → Docker build check |
| `docker-publish.yml`    | Push to main, `v*` tags | Build + push to GHCR, cosign image signing, SBOM                                      |
| `codeql.yml`            | Push + weekly           | Security-extended static analysis                                                     |
| `dependency-review.yml` | PRs to main             | Block HIGH/CRITICAL CVEs before merge                                                 |
| `release.yml`           | `v*` tags               | Build wheel, auto-generate changelog, create GitHub Release                           |
| `deploy-gcp.yml`        | Push to main            | Build → push to Artifact Registry → deploy to Cloud Run                               |
| `keep-alive.yml`        | Every 14 min            | Ping Render to prevent free-tier spin-down                                            |

---

## The 28 URL Features

The classifier uses 28 hand-engineered features extracted directly from the URL string — no external DNS lookups, no WHOIS queries:

`has_ip` · `url_length` · `has_shortener` · `has_at_symbol` · `double_slash_redirect` · `hyphen_in_domain` · `subdomain_depth` · `https_in_domain_text` · `digit_ratio` · `special_char_count` · `slash_count` · `dot_count` · `suspicious_keywords` · `domain_length` · `has_exe_extension` · `hyphen_count` · `encoded_chars` · `path_depth` · `query_length` · `domain_entropy` · `suspicious_tld` · `brand_in_subdomain` · `non_standard_port` · `digit_in_domain` · `url_entropy` · `repeated_chars` · `dangerous_extension` · `subdomain_count`

A known-legitimate domain allowlist (Google, GitHub, ChatGPT, Coursera, etc.) suppresses false positives on deep URLs that would otherwise trigger length, entropy, or path-depth features.

---

## Environment Variables

| Variable          | Required   | Default                        | Description                                                                  |
| ----------------- | ---------- | ------------------------------ | ---------------------------------------------------------------------------- |
| `SECRET_KEY`      | Yes (prod) | dev fallback                   | Flask session signing key. Generate: `python scripts/generate_secret_key.py` |
| `MODEL_PATH`      | No         | `models/phishing_model.joblib` | Absolute path to trained model                                               |
| `PORT`            | No         | `5000`                         | Server port                                                                  |
| `WEB_CONCURRENCY` | No         | `(2×CPU)+1`                    | Gunicorn worker count                                                        |
| `LOG_LEVEL`       | No         | `info`                         | `debug` / `info` / `warning` / `error`                                       |

Copy `.env.example` to `.env` and fill in real values. Never commit `.env`.

---

## Contributing

See [`.github/pull_request_template.md`](./.github/pull_request_template.md) for the PR checklist.

```bash
# Before opening a PR
make check        # lint + format check
make test         # full suite
make test-fast    # quick feedback during development
```

---

## License

MIT — see [LICENSE](./LICENSE).
