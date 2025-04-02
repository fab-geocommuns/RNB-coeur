#! /bin/bash

set -x

CLEANUP=true

cat Ramses_out_2.csv | sed 's/ext_id/numero_uai/' > guesses_benchmarked_tmp.csv

# Convert input to actual comma separated values
csvformat -d ";" -D "," fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre.csv > fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre_tmp.csv

# Left join with input on ext_id
csvjoin --left -c "numero_uai" fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre_tmp.csv guesses_benchmarked_tmp.csv > ramses_results.csv

if [ "$CLEANUP" = true ]; then
    # Remove temporary files
    rm fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre_tmp.csv
    rm guesses_benchmarked_tmp.csv
fi
