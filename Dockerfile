# syntax=docker/dockerfile:1.6

# Prepare two stages (one per arch).
FROM ghcr.io/home-assistant/amd64-base-python:3.13-alpine3.22 AS base_amd64
FROM ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.22 AS base_arm64

# Select the right stage based on TARGETARCH.
# For linux/amd64 => TARGETARCH=amd64 -> base_amd64
# For linux/arm64 => TARGETARCH=arm64 -> base_arm64
ARG TARGETARCH
FROM base_$TARGETARCH AS final

ENV PATH="/opt/venv/bin:$PATH" \
    PIP_NO_CACHE_DIR=1

RUN python -m venv /opt/venv

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY godaikin /app/godaikin

COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD [ "/run.sh" ]