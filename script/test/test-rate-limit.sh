#!/bin/bash

prompt_continue() {
    read -p "Press Enter to continue"
}

stress()
{
    local method="${1}"
    local target_url="${2}"
    local num_requests="${3}"
    local num_concurrent="${4:-${num_requests}}"
    echo "  > Sending $num_requests concurrent requests to $target_url"
    seq $num_requests | xargs -n1 -P $num_concurrent curl -s -o /dev/null -w "%{http_code}\n" -X $method $target_url | sort | uniq -c
}

main() {
    local base_origin="$1"

    if [ -z "$base_origin" ]; then
        echo "Usage: $0 <base_origin>"
        exit 1
    fi

    # Use curl to test the Nginx configuration
    # Limit is supposed to be 50 concurrent requests per ip

    echo "--> Testing 50 concurrent requests to / (expected ~20 to pass)"
    stress GET $base_origin 50

    prompt_continue

    echo "--> Testing 50 concurrent requests to /api/alpha/buildings/xxx/ (expected ~20 to pass)"
    stress GET $base_origin/api/alpha/buildings/11117H922PGK/ 50

    prompt_continue

    echo "--> Testing 50 concurrent requests to /api/alpha/tiles/xxx/xxx/xxx.pbf (expected all to pass)"
    stress GET $base_origin/api/alpha/tiles/33204/22544/16.pbf?only_active_and_real=false 50

    prompt_continue

    echo "--> Testing 20 concurrent GET requests to /admin/login (expected all to pass)"
    stress GET $base_origin/admin/login/ 20

    prompt_continue

    echo "--> Testing 20 concurrent POST requests to /admin/login (expected ~1 to pass with 403)"
    stress POST $base_origin/admin/login/ 20

    prompt_continue

    echo "--> Testing 50 concurrent GET requests to /.env (expected ~20 to pass with 404)"
    stress GET $base_origin/.env 50
}

main $@
