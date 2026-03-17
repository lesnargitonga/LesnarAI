FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENGINEIO_ASYNC_MODE=threading

# System deps (psycopg2-binary doesn’t require pg-dev)
RUN pip install --no-cache-dir --upgrade pip

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend

# The build context is the repo root; copy simulator sources too.
COPY drone_simulation /app/drone_simulation
ENV PYTHONPATH=/app/backend:/app/drone_simulation

EXPOSE 5000

WORKDIR /app/backend

CMD ["gunicorn", "-w", "1", "--threads", "8", "-b", "0.0.0.0:5000", "wsgi:app"]
