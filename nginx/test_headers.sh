#!/usr/bin/env bash
# Checks the response headers set by the nginx image: HSTS, rate limit headers, hidden nginx version.
# Builds the image, runs it in front of a dummy backend with a self-signed certificate, then curls it.
# Usage: nginx/test_headers.sh (needs docker and openssl; uses port 8443, override with PORT=...)
set -euo pipefail

cd "$(dirname "$0")"

NAME=rnb-nginx-test
HOST=rnb.test
PORT=${PORT:-8443}
CERTS_DIR=$(mktemp -d)
FAILURES=0

cleanup() {
    docker rm -f "$NAME-proxy" "$NAME-backend" >/dev/null 2>&1 || true
    docker network rm "$NAME" >/dev/null 2>&1 || true
    rm -rf "$CERTS_DIR"
}
trap cleanup EXIT

docker build --quiet --tag "$NAME" . >/dev/null

# nginx-proxy only serves HTTPS, and only sends HSTS, for a host with a certificate.
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj "/CN=$HOST" \
    -keyout "$CERTS_DIR/$HOST.key" -out "$CERTS_DIR/$HOST.crt" 2>/dev/null

docker network create "$NAME" >/dev/null
docker run --detach --name "$NAME-backend" --network "$NAME" \
    --env VIRTUAL_HOST="$HOST" --env VIRTUAL_PORT=80 traefik/whoami:v1.10 >/dev/null
docker run --detach --name "$NAME-proxy" --network "$NAME" --publish "$PORT:443" \
    --volume "$CERTS_DIR:/etc/nginx/certs:ro" \
    --volume /var/run/docker.sock:/tmp/docker.sock:ro "$NAME" >/dev/null

request() {
    curl --silent --insecure --head --resolve "$HOST:$PORT:127.0.0.1" "$@"
}

# Wait for nginx-proxy to generate its config and route the host.
for _ in $(seq 30); do
    if [ "$(request --output /dev/null --write-out '%{http_code}' "https://$HOST:$PORT/")" = 200 ]; then
        break
    fi
    sleep 1
done

# check <label> <headers> <grep -E pattern> [absent]
check() {
    local label=$1 headers=$2 pattern=$3 expect=${4:-present}
    if echo "$headers" | grep -qiE "$pattern"; then found=present; else found=absent; fi
    if [ "$found" = "$expect" ]; then
        echo "ok    $label"
    else
        echo "FAIL  $label"
        FAILURES=$((FAILURES + 1))
    fi
}

api=$(request "https://$HOST:$PORT/api/alpha/buildings/?insee_code=38185&limit=1")
check "API: HSTS" "$api" '^strict-transport-security: max-age=31536000'
check "API: RateLimit-Limit" "$api" '^ratelimit-limit: 20'
check "API: nginx version hidden" "$api" '^server: nginx/' absent

admin=$(request "https://$HOST:$PORT/admin/login/")
check "admin login: HSTS" "$admin" '^strict-transport-security: max-age=31536000'
check "admin login: RateLimit-Limit" "$admin" '^ratelimit-limit: 1'

# The admin login allows 1 POST per second: the second one is rejected with a 429.
request --output /dev/null --request POST "https://$HOST:$PORT/admin/login/"
rejected=$(request --request POST "https://$HOST:$PORT/admin/login/")
check "admin login 429: status" "$rejected" '^HTTP/[0-9.]+ 429'
check "admin login 429: HSTS" "$rejected" '^strict-transport-security: max-age=31536000'
check "admin login 429: RateLimit-Limit" "$rejected" '^ratelimit-limit: 1'

if [ "$FAILURES" -gt 0 ]; then
    echo "$FAILURES check(s) failed"
    exit 1
fi
echo "All checks passed"
