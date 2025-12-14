#!/bin/bash

# Define the URL and maximum retries
URL="https://localhost:443/health"
MAX_RETRIES=30
SLEEP_SECONDS=2

echo "Starting health check for $URL..."

count=0
while [ $count -lt $MAX_RETRIES ]; do
  # -k ignores self-signed certs (insecure)
  # --fail causes curl to return exit code 22 if HTTP status is >= 400
  # --silent hides the progress bar
  if curl -k --fail --silent "$URL" > /dev/null; then
    echo "✅ Health check passed!"
    exit 0
  fi

  echo "⏳ Waiting for service to be up... (Attempt $((count+1))/$MAX_RETRIES)"
  sleep $SLEEP_SECONDS
  count=$((count+1))
done

echo "❌ Health check failed after $MAX_RETRIES attempts."
# Print docker logs to help debugging
echo "--- DOCKER LOGS ---"
docker compose logs
exit 1
