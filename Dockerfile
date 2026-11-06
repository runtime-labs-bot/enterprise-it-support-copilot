# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt /tmp/copilot-requirements.txt
COPY backend/requirements.txt /tmp/meridian-requirements.txt
RUN python -m pip install -r /tmp/copilot-requirements.txt -r /tmp/meridian-requirements.txt
COPY app ./app
COPY backend/app /opt/meridian/app
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/checkpoints \
    && chown -R appuser:appuser /app/data
USER appuser
EXPOSE 8001
CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
