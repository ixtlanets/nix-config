FROM python:3.13.7-slim-bookworm@sha256:781449467ffb6f04218f09b1ecdcdc7d22b289ee5da9ec498b024e24ad7a6db7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY scripts/worker.py ./scripts/worker.py
COPY bin/audiobookctl /usr/local/bin/audiobookctl
COPY --chmod=0755 scripts/container-entrypoint.py /usr/local/bin/audiobook-ops-entrypoint

USER 0:0

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/audiobook-ops-entrypoint"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
