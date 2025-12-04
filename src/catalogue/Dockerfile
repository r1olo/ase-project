FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/catalogue /app/catalogue
COPY src/common /app/common

RUN mkdir -p /app/cards
COPY cards/cards.json /app/cards/cards.json

EXPOSE 5000

CMD ["flask", "--app=catalogue.app", "run", "--cert=/run/secrets/catalogue.crt", "--key=/run/secrets/catalogue.key", "--host=0.0.0.0", "--port=5000"]
