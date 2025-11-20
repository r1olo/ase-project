# Multi-stage Dockerfile for Game Engine Microservice

# ============== BUILD STAGE ==============
FROM python:3.11-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/game_engine /app/game_engine
COPY src/common /app/common

EXPOSE 5000

CMD ["flask", "--app=game_engine.app", "run", "--host=0.0.0.0", "--port=5000"]
