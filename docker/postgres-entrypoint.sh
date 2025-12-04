#!/bin/sh
POSTGRES_CERT=${POSTGRES_CERT:-/run/secrets/postgres.crt}
POSTGRES_KEY=${POSTGRES_KEY:-/run/secrets/postgres.key}

cp $POSTGRES_KEY /tmp/server.key && \
    chmod 600 /tmp/server.key && \
    chown postgres:postgres /tmp/server.key && \
    cp $POSTGRES_CERT /tmp/server.crt && \
    docker-entrypoint.sh postgres -c ssl=on \
    -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key
