# Repository Guidelines

## Project Structure & Module Organization
- `json-collector-service.py` hosts the Flask + Tornado application, request logging, and file rotation logic; keep new routes colocated with existing helpers.
- `Dockerfile` builds the Python 3.13 image, exposing port 8000 and mounting `/run/collector` for JSONL output.
- `launch-json-collector-service-docker.sh` wraps image build and container run; treat it as the canonical deployment entrypoint.
- `README.md` documents usage scenarios; update it when behavior or CLI flags change.

## Build, Test, and Development Commands
Initialize a Python 3.13 virtual environment and install dependencies before local work:
```shell
python -m venv .venv && source .venv/bin/activate
pip install -r requires.txt
```
Common workflows:
```shell
python json-collector-service.py          # run the app on localhost:8000
./launch-json-collector-service-docker.sh /absolute/path/to/data  # build & run via Docker
docker build -t json-collector-service:latest .  # rebuild the container image
```

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and snake_case identifiers; module-level constants stay capitalized.
- Flask route handlers should return plain strings or `send_from_directory` responses and call shared helpers like `log_request_event`.
- Keep helper functions pure where possible and avoid side effects outside `DATA_FILE_DIR`.
- Prefer `json.dumps` for serialization and reuse `log_request_event` for consistent auditing.

## Testing Guidelines
- Automated coverage lives in `tests/test_json_collector_service.py`, exercising health checks, ingestion, and file rotation.
- Run `python3 -m unittest discover` (or `pytest`) from the repo root after installing `flask` and `tornado` via `requires.txt`.
- Malformed payload tests (e.g., posting non-JSON bodies) should assert the collector returns HTTP 400; note that these error cases only log to stdout and do not append to the JSONL file.
- Adjust `MAX_JSONL_FILE_SIZE` to small byte values during tests if you need to observe rotation behavior manually.
- When adding endpoints, pair them with request/response assertions alongside any exploratory `curl` commands you document in PRs.

## Commit & Pull Request Guidelines
- Mirror the existing history: concise, imperative commit subjects (e.g., "add dataset throttle guard") and focused diffs.
- Reference related issues in the body, summarize runtime/testing evidence, and note config changes such as new env vars or ports.
- PRs should explain operational impact, include Docker commands used for validation, and call out breaking changes.

## Configuration & Operations Tips
- Override defaults with environment variables: `MAX_JSONL_FILE_SIZE` controls JSONL rotation thresholds, and `DATA_FILE_DIR` is set via volume mounts.
- When running outside Docker, ensure `DATA_FILE_DIR` points to a writable directory you can inspect; invalid payloads won’t create JSONL entries, so check the service logs to audit parse failures.
- Expose port 8000 only to trusted networks; consider fronting the container with TLS and access controls for production deployments.
