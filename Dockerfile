# One image for both Compose services: `api` runs the default CMD, `streamlit` overrides it.
# The build needs no OPENAI_API_KEY and no model provider: model settings arrive at runtime
# from Compose, and .dockerignore keeps .env out of the build context.
FROM python:3.11-slim

# PYTEST_ADDOPTS: the code is read-only for the app user, so pytest must not write .pytest_cache.
# STREAMLIT_*: no browser inside a container, and no usage statistics sent anywhere.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTEST_ADDOPTS="-p no:cacheprovider" \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependencies first, so this layer stays cached while only the code changes.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Only what the services, the seed, the tests, and the evaluator read at runtime.
# pyproject.toml carries the pytest settings (pythonpath, the `live` marker).
COPY pyproject.toml app.py ui_contract.py ui_format.py demo_personas.json ./
COPY src/ ./src/
COPY data/ ./data/
COPY evaluation/ ./evaluation/
COPY tests/ ./tests/

# Non-root user. The code stays owned by root, so the running app cannot change it. The user
# can write only to its home (Streamlit) and to /app/outputs (evaluation reports, exported
# with `docker compose cp api:/app/outputs ./outputs`).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/outputs \
    && chown appuser:appuser /app/outputs
USER appuser

EXPOSE 8000 8501

# Plain CMD, no ENTRYPOINT: Compose replaces it for Streamlit, and `docker compose run api ...`
# replaces it for the seed and the tests.
CMD ["python", "-m", "uvicorn", "src.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
