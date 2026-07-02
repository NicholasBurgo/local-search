# Deploying the Leadfinder web app

`leadfinder serve` is a normal HTTP service, so it hosts like any web app. It
needs outbound internet (Overture S3, Nominatim geocoding, and domain probing)
but no inbound secrets - Overture is keyless, so there is nothing to configure.

## Run locally

```bash
uv run leadfinder serve            # http://127.0.0.1:8000
uv run leadfinder serve --host 0.0.0.0 --port 8080   # expose on your LAN
```

## Docker (any host)

```bash
docker build -t leadfinder .
docker run -p 8000:8000 -e SEARCH_CITIES="Covington LA" leadfinder
# open http://localhost:8000
```

## Render / Railway / Fly.io (one service, from the Dockerfile)

- **Runtime:** Docker (use the included `Dockerfile`), or a plain Python service
  running `uv run leadfinder serve --host 0.0.0.0 --port $PORT`.
- **Port:** bind `$PORT` (the Dockerfile already does).
- **Env (optional):** `SEARCH_CITIES` (default initial location), `OVERTURE_RELEASE`.
- **No database, no secrets, no API key.**

### Fly.io
```bash
fly launch --dockerfile Dockerfile
fly deploy
```

### Render
New Web Service -> connect the repo -> it detects the `Dockerfile`. Health check
path `/`.

## Notes

- **OSM tiles + Nominatim** public services are fine for personal / low-traffic
  use. For a high-traffic public deployment, run your own tile + geocoding
  (see their usage policies) to stay within limits.
- The **first Overture query per container** downloads the DuckDB `httpfs`
  extension (a few seconds); later queries are faster.
- **Verify** makes outbound HTTP requests to probe candidate domains - allow egress.
- A bigger radius scans a larger Overture area (slower, more results); the UI
  caps the slider at 30 mi.
