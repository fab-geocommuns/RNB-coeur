#!/bin/bash

source .env

if [ -z "$JUMP_SERVER_USER" ] || [ -z "$JUMP_SERVER_HOST" ] || [ -z "$DB_SERVER_HOST" ] || [ -z "$DB_SERVER_PORT" ] || [ -z "$LOCAL_PORT" ]; then
    echo "Error: Missing required environment variables in .env file."
    exit 1
fi

echo "Creating SSH tunnel..."
ssh -i "$JUMP_SERVER_PKEY" -N -L "$LOCAL_PORT:$DB_SERVER_HOST:$DB_SERVER_PORT" "$JUMP_SERVER_USER@$JUMP_SERVER_HOST" -p "$JUMP_SERVER_PORT" &

SSH_PID=$!

echo -e "\nTunnel opened: localhost:$LOCAL_PORT -> $DB_SERVER_HOST:$DB_SERVER_PORT.\nCtrl+C to stop."

cleanup() {
    echo "Stopping SSH tunnel..."
    kill "$SSH_PID"
    echo "Tunnel stopped."
    exit 0
}

trap cleanup EXIT SIGINT SIGTERM

wait "$SSH_PID"
