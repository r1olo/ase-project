FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src/api_gateway /app/api_gateway
COPY src/common /app/common

EXPOSE 80

CMD ["flask", "--app=api_gateway.app", "run", "--host=0.0.0.0", "--port=80"]
