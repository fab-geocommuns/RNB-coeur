#!/bin/bash

prompt_continue() {
    read -p "Press Enter to continue"
}

main() {
    local target_url="$1"

    if [ -z "$target_url" ]; then
        echo "Usage: $0 <target_url>"
        exit 1
    fi

    # Use ab to test the Nginx configuration
    # Limit is supposed to be 50 concurrent requests per ip

    echo "--> Testing below rate limit"
    ab -n 50 -c 50 $target_url

    prompt_continue

    echo "--> Testing above absolute but below concurrent rate limit within a single IP"
    ab -n 70 -c 50 $target_url

    prompt_continue

    echo "--> Testing above concurrent rate limit within a single IP"
    ab -n 200 -c 200 $target_url

    prompt_continue

    echo "--> Testing below rate limit from different IPs"
    for i in {1..3}; do
        ab -n 30 -c 30 -H "X-Forwarded-For: 192.168.0.$i" $target_url &
    done
    wait

    prompt_continue

    echo "--> Testing above rate limit from different IPs"
    for i in {1..3}; do
        ab -n 51 -c 51 -H "X-Forwarded-For: 192.168.0.$i" $target_url &
    done
}

main $@
