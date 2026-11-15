# Runs the API the same way on any computer and on Render.
#   Build: docker build -t est-api .
#   Run:   docker run -p 8000:8000 --env-file .env est-api   then open http://localhost:8000/health
FROM python:3.12-slim

# uv at an exact version, not a moving tag
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv
WORKDIR /app

# Libraries first (cached until pyproject/uv.lock change). Backend deps only, no data/frontend.
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --locked --no-default-groups --no-install-project

# Our code plus every file the API reads at run time
COPY src ./src
COPY results.mock.json ./
COPY results ./results
COPY web ./web
RUN uv sync --locked --no-default-groups

# Render tells us the port through PORT. --proxy-headers so each visitor keeps their own address.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn earth_system_trend.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips '*'"]
