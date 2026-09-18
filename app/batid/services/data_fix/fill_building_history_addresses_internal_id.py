import logging
from typing import Optional

from batid.services.data_fix.fill_building_addresses_internal_id import (
    compute_id_slices,
)
from django.db import connection, transaction

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10_000

# batid_building_history.bh_id is a BigAutoField (bigint), unlike
# batid_building.id (a plain int4 AutoField): reusing the sibling module's
# MAX_INT4 here would silently stop the backfill early on this larger table.
MAX_BIGINT = 2**63 - 1


def fill_building_history_addresses_internal_id(
    batch_size: int = DEFAULT_BATCH_SIZE,
    min_id: int = 0,
    max_id: Optional[int] = None,
) -> int:
    """Give history rows written before migration 0149 their addresses_internal_id.

    batid_building_history has no versioning trigger of its own (it *is* the
    history table) and building_addresses_trigger / keep_building_address_link_updated()
    are attached to batid_building only, not to batid_building_history: a raw
    UPDATE here has no side effect to guard against, unlike
    fill_building_addresses_internal_id(), which must run inside
    building_versioning_dangerously_disabled().

    Every cle in a batid_building row's addresses_id is guaranteed to have a
    matching batid_address row (see fill_building_addresses_internal_id()'s
    docstring), but that guarantee is only partial for history rows:
    prevent_delete_linked_address_trigger, which blocks deleting an address
    still referenced by batid_building_history, only exists since migration
    0125 (specs/migration_lien_batiment_adresse.md). A history row written
    before that migration can reference a cle whose batid_address row has
    since been deleted. Such a cle is resolved with a LEFT JOIN and left as a
    positional NULL in addresses_internal_id (same length and order as
    addresses_id) rather than aborting the run or silently shortening the
    array. The number of cles left unresolved this way is logged per batch.

    Rows are walked in bh_id order (the primary key of BuildingHistoryOnly;
    the id column on this table mirrors batid_building.id and is not unique,
    so it cannot be used to paginate), one committed batch at a time, so the
    job can be interrupted and resumed. It only ever touches rows where
    addresses_internal_id IS NULL, so it never overwrites a value already
    written and running it twice is harmless.

    min_id/max_id restrict the scan to a slice of the bh_id space (min_id
    exclusive, max_id inclusive, like the batch bounds themselves), so
    several calls can run in parallel over disjoint ranges. This table is the
    largest volume of the migration (specs/migration_lien_batiment_adresse.md),
    so running it as several parallel Celery tasks matters even more here
    than for fill_building_addresses_internal_id().

    Returns the number of history rows that received an addresses_internal_id.
    """
    updated = 0
    orphan_cles = 0
    last_id = min_id

    with connection.cursor() as cursor:
        # The worker connection carries a statement timeout of a few seconds,
        # which a batch of this size does not fit in.
        cursor.execute("SET statement_timeout = '0';")

        while True:
            # Take the batch bounds first, over every history row regardless
            # of addresses_internal_id: a page made only of already filled or
            # address-less rows must still advance, or the loop never ends.
            cursor.execute(
                """
                SELECT max(bh_id) FROM (
                    SELECT bh_id FROM batid_building_history
                    WHERE bh_id > %s AND bh_id <= %s
                    ORDER BY bh_id LIMIT %s
                ) AS batch;
                """,
                [last_id, max_id if max_id is not None else MAX_BIGINT, batch_size],
            )
            batch_max_id = cursor.fetchone()[0]

            if batch_max_id is None:
                break

            with transaction.atomic():
                cursor.execute(
                    """
                    WITH resolved AS (
                        UPDATE batid_building_history bh
                        SET addresses_internal_id = COALESCE(
                            (
                                SELECT array_agg(a.internal_id ORDER BY u.ord)
                                FROM unnest(bh.addresses_id) WITH ORDINALITY AS u(cle, ord)
                                LEFT JOIN batid_address a ON a.id = u.cle
                            ),
                            '{}'
                        )
                        WHERE bh.bh_id > %s AND bh.bh_id <= %s
                          AND bh.addresses_internal_id IS NULL
                          AND bh.addresses_id IS NOT NULL
                        RETURNING
                            cardinality(bh.addresses_id) AS n_keys,
                            cardinality(array_remove(bh.addresses_internal_id, NULL)) AS n_resolved
                    )
                    SELECT count(*), coalesce(sum(n_keys - n_resolved), 0) FROM resolved;
                    """,
                    [last_id, batch_max_id],
                )
                batch_updated, batch_orphans = cursor.fetchone()
                updated += batch_updated
                orphan_cles += batch_orphans

            last_id = batch_max_id
            logger.info(
                "fill_building_history_addresses_internal_id: %s history rows filled "
                "(%s orphan cles so far), up to bh_id %s",
                updated,
                orphan_cles,
                last_id,
            )

    if orphan_cles:
        logger.warning(
            "fill_building_history_addresses_internal_id: %s cle(s) in addresses_id "
            "had no matching batid_address row and were left as NULL in "
            "addresses_internal_id",
            orphan_cles,
        )

    return updated
