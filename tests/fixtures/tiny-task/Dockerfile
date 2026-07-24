# Minimal environment for the tiny self-verification task.
# git is required so reforge can snapshot a base commit and capture the diff.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest==8.2.2

WORKDIR /workspace
