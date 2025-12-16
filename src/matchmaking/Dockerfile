FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/matchmaking /app/matchmaking
COPY src/common /app/common

EXPOSE 5000

#CMD ["flask", "--app=matchmaking.app", "run", "--cert=/run/secrets/matchmaking.crt", "--key=/run/secrets/matchmaking.key", "--host=0.0.0.0", "--port=5000"]
CMD ["gunicorn", "--workers=4", "--threads=8", "--bind=0.0.0.0:5000", "--certfile=/run/secrets/matchmaking.crt", "--keyfile=/run/secrets/matchmaking.key", "matchmaking.app:create_app()"]
