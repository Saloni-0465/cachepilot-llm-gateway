FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin cachepilot

USER cachepilot

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "cachepilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
