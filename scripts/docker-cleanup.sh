#!/bin/sh
docker compose rm
docker rmi $(docker images | grep 'ase-project' | awk '{print $1}')
docker volume rm $(docker volume ls | grep 'ase-project' | awk '{print $2}')
