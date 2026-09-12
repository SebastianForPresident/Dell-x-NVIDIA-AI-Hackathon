FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY forensics.py persistence.py investigations.py agent_assets.py agent_tools.py ./
COPY server/ ./server/
COPY --from=web /web/dist ./static/
ENV STATIC_DIR=/app/static
ENV CROP_ASSET_DIR=/data/case_assets
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
