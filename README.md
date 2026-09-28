# RaptorGate (DOGFOOD 2026 rewrite)

A new implementation started September 28, 2026 inside the official build window. This is a work in progress, not a completed submission.

## Run locally

Requires Docker Compose. Download images and install dependencies once while online:

```
docker compose build
docker compose pull db
docker compose up
```

After the images are available, `docker compose up` starts PostgreSQL and the Django portal, migrates, and seeds the official fixture event if empty. Open http://localhost:8080/projects. The portal binds loopback only. Do not expose these local demo credentials publicly.

Run the official checker against the local stack:

```
python3 run.py .dogfood.toml > acceptance-report.txt
cat acceptance-report.txt
```

Run project tests with `python src/manage.py test eventhub.tests`, or install `requirements-dev.txt` and run `PYTHONPATH=src pytest -q`. The current implementation is T1/T2 acceptance-first. There is not yet a complete event lifecycle, UI for assignment/scoring, normalization, or a demo video. Do not claim more than the fresh report verifies.
