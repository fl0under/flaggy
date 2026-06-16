FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash curl ca-certificates file binutils git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY workdir/ /app/

RUN mkdir -p /logs/artifacts/evidence
