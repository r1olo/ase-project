#!/bin/sh

FOLDER=secrets
SERVICES=(
    auth{,-db}
    players{,-db}
    game_engine{,-db}
    matchmaking{,-db}
    catalogue{,-db}
)

echo "Generating certificates and keys..."
{
    mkdir -p $FOLDER

    openssl genrsa -out $FOLDER/jwtRS256.key 2048
    openssl rsa -in secrets/jwtRS256.key -pubout -out $FOLDER/jwtRS256.key.pub

    for ser in "${SERVICES[@]}"; do
        openssl req -x509 -newkey rsa:4096 -nodes -out "$FOLDER/$ser.crt" \
            -keyout "$FOLDER/$ser.key" -days 365 -subj "/CN=$ser" \
            -addext "subjectAltName=DNS:$ser,DNS:localhost,IP:127.0.0.1"
    done
} &>/dev/null && echo "Certificates and keys generated"
