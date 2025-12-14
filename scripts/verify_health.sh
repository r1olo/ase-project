#!/bin/bash

# Define the URL and maximum retries
REGISTER_URL="https://localhost:443/register"
MAX_RETRIES=30
SLEEP_SECONDS=2

echo "Starting health check by registrating one user"

count=0
while [ $count -lt $MAX_RETRIES ]; do
  # -k ignores self-signed certs (insecure)
  # --fail causes curl to return exit code 22 if HTTP status is >= 400
  # --silent hides the progress bar
  curl -k --fail --silent "$REGISTER_URL" \
      -H "Content-Type: application/json" \
      -d '{"email": "me@me.dev", "password": "me"}' \
      >/dev/null && { echo "Health check complete"; exit 0; }

  echo "Waiting for service to be up... (Attempt $((count+1))/$MAX_RETRIES)"
  sleep $SLEEP_SECONDS
  count=$((count+1))
done

echo "Health check failed after $MAX_RETRIES attempts."
# Print docker logs to help debugging
echo "--- DOCKER LOGS ---"
docker compose logs
exit 1
