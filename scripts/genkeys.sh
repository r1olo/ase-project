#!/bin/bash
FOLDER=secrets
AUTH_DB_ENC=auth_db_encryption.key
SERVICES=(
    auth{,-db}
    players{,-db}
    game-engine{,-db}
    matchmaking{,-db}
    catalogue{,-db}
    nginx
)

echo "Generating certificates and keys..."
{
    [ -d $FOLDER ] && rm -rf $FOLDER
    mkdir -p $FOLDER

    openssl genrsa -out $FOLDER/jwtRS256.key 2048
    openssl rsa -in secrets/jwtRS256.key -pubout -out $FOLDER/jwtRS256.key.pub

    for ser in "${SERVICES[@]}"; do
        openssl req -x509 -newkey rsa:4096 -nodes -out "$FOLDER/$ser.crt" \
            -keyout "$FOLDER/$ser.key" -days 365 -subj "/CN=$ser" \
            -addext "subjectAltName=DNS:$ser,DNS:localhost,IP:127.0.0.1"
    done
} &>/dev/null && echo "Certificates and keys generated"

echo "Generating Auth DB encryption key..."
openssl rand -base64 32 >$FOLDER/$AUTH_DB_ENC
