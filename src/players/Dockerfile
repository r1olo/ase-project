FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/players /app/players
COPY src/common /app/common

EXPOSE 5000

CMD ["flask", "--app=players.app", "run", "--cert=/run/secrets/players.crt", "--key=/run/secrets/players.key", "--host=0.0.0.0", "--port=5000"]
