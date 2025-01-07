#!/bin/bash
# This script updates the metabase docker container from the docker-compose.prod.yml

# Pull the latest docker image
docker pull metabase/metabase

# Move to the docker-compose.prod.yml folder (this script is not path dependant)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$TARGET_DIR" || exit

# Recreate the metabase container only
docker compose -f docker-compose.prod.yml up -d --no-deps --build metabase

# Remove unused docker images
docker image prune -f
