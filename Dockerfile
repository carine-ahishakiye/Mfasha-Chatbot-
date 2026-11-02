
FROM python:3.11-slim

ARG INSTALL_ML=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt requirements-ml.txt ./
RUN pip install -r requirements.txt \
 && if [ "$INSTALL_ML" = "true" ]; then pip install -r requirements-ml.txt; fi

COPY pyproject.toml ./
COPY src ./src
COPY frontend ./frontend
COPY data/sample ./data/sample
RUN pip install --no-deps -e .

RUN useradd --create-home appuser && mkdir -p /app/models && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "-c", "uvicorn mfasha.api.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
