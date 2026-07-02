# Leadfinder web app - interactive lead map over Overture open data (no API key).
FROM python:3.12-slim

# uv (fast installer + runner) from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
COPY . .

# Install runtime dependencies into a project venv (skip dev deps)
RUN uv sync --frozen --no-dev

# Default initial location (searchable in the UI); override at deploy time.
ENV SEARCH_CITIES="Covington LA"
ENV PORT=8000
EXPOSE 8000

# Bind 0.0.0.0 for the container; hosts inject $PORT.
CMD ["sh", "-c", "uv run --no-dev leadfinder serve --host 0.0.0.0 --port ${PORT:-8000}"]
