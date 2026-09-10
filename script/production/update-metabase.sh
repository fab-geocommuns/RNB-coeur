#!/bin/bash
# This script updates the metabase docker container from the docker-compose.prod.yml

# Move to the docker-compose.prod.yml folder (this script is not path dependant)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$TARGET_DIR" || exit

# Pull the image version pinned in docker-compose.common.yml
docker compose -f docker-compose.prod.yml pull metabase || exit

# Recreate the metabase container only
docker compose -f docker-compose.prod.yml up -d --no-deps metabase

# Remove unused docker images
docker image prune -f
