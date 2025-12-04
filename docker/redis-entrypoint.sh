#!/bin/sh
set -e

# 1. Define where we will copy the certs so Redis can read them
# We use /tmp because it's usually a ramdisk (fast/secure) and writable
DEST_CERT="/tmp/redis.crt"
DEST_KEY="/tmp/redis.key"
DEST_CA="/tmp/ca.crt"

echo "Setting up Redis TLS permissions..."

# 2. Check if the environment variables for secret paths are set
if [ -z "$TLS_CERT_SECRET" ] || [ -z "$TLS_KEY_SECRET" ]; then
    echo "Error: TLS_CERT_SECRET and TLS_KEY_SECRET env vars must be set."
    exit 1
fi

# 3. Copy the secrets from the read-only root mount to /tmp
cp "$TLS_CERT_SECRET" "$DEST_CERT"
cp "$TLS_KEY_SECRET" "$DEST_KEY"
# Assuming the CA is the same as the cert for self-signed, or pass a separate env var
cp "$TLS_CERT_SECRET" "$DEST_CA" 

# 4. Fix permissions (Give ownership to the redis user:group)
# Alpine Redis user is usually 'redis' (uid 999)
chown redis:redis "$DEST_CERT"
chown redis:redis "$DEST_KEY"
chown redis:redis "$DEST_CA"

chmod 644 "$DEST_CERT"
chmod 600 "$DEST_KEY"
chmod 644 "$DEST_CA"

echo "Permissions fixed. Starting Redis with TLS..."

# 5. Execute Redis using su-exec to drop privileges from root -> redis
# We hardcode the tls paths to the NEW locations in /tmp
exec gosu redis redis-server \
    --tls-port 6379 \
    --port 0 \
    --tls-cert-file "$DEST_CERT" \
    --tls-key-file "$DEST_KEY" \
    --tls-ca-cert-file "$DEST_CA" \
    --save "" \
    --appendonly "no"
