# Build on the GB10 while setup network access is available.
# Runtime inference goes only through OpenShell's local route.
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/nvidia/openshell-community/sandboxes/base:latest
USER root
COPY requirements.txt /tmp/crop-forensics-requirements.txt
RUN python3 -m venv /opt/crop-forensics-venv \
    && /opt/crop-forensics-venv/bin/python -m pip install --no-cache-dir -r /tmp/crop-forensics-requirements.txt
ENV PATH="/opt/crop-forensics-venv/bin:${PATH}"
ENV STATIC_DIR=/app/static
ENV MONGO_URI=mongodb://host.openshell.internal:27017
WORKDIR /app
COPY forensics.py local_narrative.py ./
COPY server/ ./server/
COPY scripts/gb10_preflight.py ./scripts/gb10_preflight.py
COPY --from=web /web/dist ./static/
USER sandbox
EXPOSE 8000
