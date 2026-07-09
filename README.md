# PhishGuard

**Built by [RAHUL K P](https://github.com/rahulkp-ai) — ML Engineer · GenAI · MSc CS @ 2026**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-rahulkp--ai-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/rahulkp-ai/)
[![Kaggle](https://img.shields.io/badge/Kaggle-rahulkpai-20BEFF?style=flat-square&logo=kaggle&logoColor=white)](https://www.kaggle.com/rahulkpai)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0009--3403--6670-A6CE39?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0009-3403-6670)

<br/>

PhishGuard is an ML-powered phishing URL detection service built with Flask, scikit-learn, and Prometheus instrumentation. It provides a web UI, REST API, batch prediction support, and containerized deployment options.

## Features

- URL phishing detection using a trained machine learning model
- Single URL prediction endpoint (`/api/predict`)
- Batch prediction endpoint (`/api/batch`)
- Health endpoint (`/api/health`) and metrics endpoint (`/metrics`)
- Flask web UI for manual URL scanning
- Docker and Docker Compose support for development and production
- Training pipeline for dataset construction and model generation

## Quick Start

### 1. Install dependencies

```bash
python3 -m pip install -e .
```

### 2. Train the model

The service requires `models/phishing_model.joblib` before it can serve predictions.

```bash
make train
```

If you already have the URL data files in `data/processed`, use:

```bash
make train-fast
```

### 3. Run locally

```bash
make run
```

Open the app at:

```bash
http://localhost:5005/
```

### 4. Run tests

```bash
make test
```

## Running in Docker

### Build the image

```bash
make docker-build
```

### Run a production container

```bash
make docker-run SECRET_KEY=$(python scripts/generate_secret_key.py)
```

> Note: the production container requires `SECRET_KEY` to be set.

### Docker Compose

- Development service with hot reload: `docker compose -f docker/docker-compose.yml up dev`
- Production service: `docker compose -f docker/docker-compose.yml up prod`

## Local development

### Install editable package and dev dependencies

```bash
make install
```

### Useful commands

```bash
make lint
make lint-fix
make format
make test-fast
make run-prod
```

## API reference

### Health

```http
GET /api/health
```

Response example:

```json
{
  "status": "ok",
  "model_loaded": true,
  "num_features": 28
}
```

### Predict a single URL

```http
POST /api/predict
Content-Type: application/json

{ "url": "http://example.com" }
```

Response example:

```json
{
  "url": "http://example.com",
  "is_phishing": false,
  "label": "LEGITIMATE",
  "phishing_pct": 10.0,
  "legit_pct": 90.0,
  "confidence": 90.0,
  "risk_level": "SAFE",
  "features": { ... },
  "analysis_time_ms": 15.34
}
```

### Batch prediction

```http
POST /api/batch
Content-Type: application/json

{ "urls": ["https://google.com", "http://malicious.site"] }
```

### Prometheus metrics

```http
GET /metrics
```

## Configuration

The application supports environment configuration via `app/config.py` and a few runtime environment variables:

- `SECRET_KEY` — required in production
- `PORT` — server port (default `5005` for local run; set `PORT=5005` for Docker Compose)
- `MODEL_PATH` — path to the model file, default `models/phishing_model.joblib`
- `WEB_CONCURRENCY` — number of Gunicorn workers for production

## Project structure

- `app/` — Flask application factory, routes, middleware, templates
- `src/phishguard/` — reusable package for data loading, feature extraction, model training, and metrics
- `docker/` — Dockerfile, Gunicorn config, compose files
- `deploy/` — deployment automation and platform guides
- `data/` — raw and processed datasets
- `models/` — trained model artifact
- `scripts/` — training pipeline and secret key generation
- `tests/` — unit and integration tests

## Deployment

Deployment guidance is available under `deploy/` for:

- Render
- GCP Cloud Run
- Kubernetes

## Notes

- `make run` starts the Flask development server with hot reload on port `5005`.
- The production entrypoint is `python run.py --prod`.
- If you run the Docker image directly, set `PORT=5005` when binding to port `5005`.

## License

This project is licensed under the terms in `LICENSE`.
