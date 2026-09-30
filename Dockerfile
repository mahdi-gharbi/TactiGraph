FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir uv==0.6.14
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
COPY configs/ ./configs/
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_HTTP_TIMEOUT=120 uv sync --frozen --no-dev --no-editable
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --create-home app && mkdir -p /app/data && chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH" TACTIGRAPH_MODE=public
EXPOSE 8000
CMD ["sh", "-c", "tactigraph serve --host 0.0.0.0 --port ${PORT:-8000}"]
