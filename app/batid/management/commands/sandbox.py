import cProfile
import io
import pstats

from django.core.management.base import BaseCommand
import fiona
from batid.services.source import Source

from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        src = Source("bdtopo")
        src.set_params({"dpt": "001", "projection": "LAMB93", "date": "2025-12-15"})
        path = src.find(src.filename)

        print(f"Opening file at path: {path}")

        error_count = 0

        with fiona.open(path, layer="batiment") as layer:
            # Create a manual iterator
            iterator = iter(layer)

            while True:
                try:
                    # Manually retrieve the next feature
                    feature = next(iterator)

                    # --- Your processing logic here ---
                    print(feature["properties"]["cleabs"])
                    # create_candidate_from_bdtopo(...)

                except StopIteration:
                    # The loop has finished
                    break
                except ValueError as e:
                    error_count += 1
                    # This catches the "second must be in 0..59" error
                    print(f"⚠️ SKIPPING BAD FEATURE due to invalid date: {e}")
                    # Since we are manually calling next(), the loop continues to the next item
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
                    # Decide if you want to raise or continue here
                    # raise e

        print(f"Total errors encountered: {error_count}")
