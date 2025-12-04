#!/bin/sh
docker compose rm
docker rmi $(docker images | grep 'ase-project' | awk '{print $1}')
