#! /bin/bash

set -x

CLEANUP=true

# Use csvcut to extract only columns ext_id,matches,match_reason,valid,comment from guesses_benchmark.csv
# and rename ext_id to "CODE COMPLET" as expected by the input
csvcut -c ext_id,matches,match_reason,valid,comment guesses_benchmarked.csv | sed 's/ext_id/CODE COMPLET/' > guesses_benchmarked_tmp.csv

# Convert SM.csv to actual comma separated values 
csvformat -d ";" -D "," SM.csv > SM_tmp.csv

# Left join with SM.csv (input) on CODE COMPLET
csvjoin -c "CODE COMPLET" SM_tmp.csv guesses_benchmarked_tmp.csv > saint_malo_results.csv

if [ "$CLEANUP" = true ]; then
    # Remove temporary files
    rm SM_tmp.csv
    rm guesses_benchmarked_tmp.csv
fi

