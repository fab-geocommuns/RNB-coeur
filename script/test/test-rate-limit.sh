#!/bin/bash

prompt_continue() {
    read -p "Press Enter to continue"
}

stress() {
    local target_url="$1"
    local num_requests="$2"
    local num_concurrent="$3"
    echo "  > Sending $num_requests concurrent requests to $target_url"
    seq $num_requests | xargs -n1 -P $num_concurrent sh -c 'sleep 1; curl -s -o /dev/null -w "%{http_code}\n" "$0"' $target_url | sort | uniq -c
}

main() {
    local target_url="$1"
    # Note: this is a high rate limiting, so testing accurately is hard. It looks like
    # the above xargs command has a hard time spawning that many concurrent requests at
    # the exact same time. You can test the overall behavior by lowering the rate here and
    # in the settings.py file.
    local rate_limit=50

    if [ -z "$target_url" ]; then
        echo "Usage: $0 <target_url>"
        exit 1
    fi

    # Use curl to test the Nginx configuration
    # Limit is supposed to be 50 concurrent requests per ip

    echo "--> Testing below rate limit"
    stress $target_url $rate_limit $rate_limit

    prompt_continue

    echo "--> Testing above rate limit but below concurrent limit"
    stress $target_url $(( rate_limit * 5 )) $rate_limit

    prompt_continue

    echo "--> Testing above rate limit"
    stress $target_url $(( rate_limit * 5 )) $(( rate_limit * 5 ))
}

main $@
