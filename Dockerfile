# Build on the GB10 host while network access is available.
# The running sandbox makes no package or cloud inference requests.
FROM ghcr.io/nvidia/openshell-community/sandboxes/base:latest

COPY requirements.txt /tmp/crop-forensics-requirements.txt
RUN python3 -m venv /opt/crop-forensics-venv \
    && /opt/crop-forensics-venv/bin/python -m pip install --no-cache-dir -r /tmp/crop-forensics-requirements.txt
ENV PATH="/opt/crop-forensics-venv/bin:${PATH}"
