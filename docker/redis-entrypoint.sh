#!/bin/sh
set -e

# Copy secrets to a place with correct permissions
cp /run/secrets/redis.crt /tls.crt
cp /run/secrets/redis.key /tls.key

chmod 600 /tls.crt /tls.key

# Start Redis with TLS only
exec redis-server \
  --tls-port 6379 \
  --port 0 \
  --tls-cert-file /tls.crt \
  --tls-key-file  /tls.key \
  --tls-ca-cert-file /tls.crt \
  --tls-auth-clients no \
  --save "" \
  --appendonly no
