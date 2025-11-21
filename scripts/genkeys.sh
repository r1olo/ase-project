#!/bin/sh

mkdir secrets

openssl genrsa -out secrets/jwtRS256.key 2048

openssl rsa -in secrets/jwtRS256.key -pubout -out secrets/jwtRS256.key.pub