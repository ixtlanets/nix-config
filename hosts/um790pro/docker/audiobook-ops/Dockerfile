FROM python:3.13.7-slim-bookworm@sha256:781449467ffb6f04218f09b1ecdcdc7d22b289ee5da9ec498b024e24ad7a6db7

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

USER 1000:1000

EXPOSE 8000

ENTRYPOINT ["python", "-m", "audiobook_ops"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
