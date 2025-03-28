#!/bin/bash

prompt_continue() {
    read -p "Press Enter to continue"
}

stress()
{
    local target_url="$1"
    local num_requests="$2"
    local num_concurrent="$3"
    echo "  > Sending $num_requests concurrent requests to $target_url"
    seq $num_requests | xargs -n1 -P $num_concurrent curl -s -o /dev/null -w "%{http_code}\n" $target_url | sort | uniq -c
}

main() {
    local target_url="$1"

    if [ -z "$target_url" ]; then
        echo "Usage: $0 <target_url>"
        exit 1
    fi

    # Use curl to test the Nginx configuration
    # Limit is supposed to be 50 concurrent requests per ip

    echo "--> Testing below rate limit"
    stress $target_url 49 49

    prompt_continue

    echo "--> Testing above rate limit but below concurrent limit"
    stress $target_url 200 49

    prompt_continue

    echo "--> Testing above rate limit"
    stress $target_url 200 200
}

main $@
