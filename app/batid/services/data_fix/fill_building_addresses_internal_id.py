import logging

from batid.utils.db import building_versioning_dangerously_disabled
from django.db import connection, transaction

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10_000


def fill_building_addresses_internal_id(batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Give buildings written before migration 0149 their addresses_internal_id.

    Buildings written since PR #1029 already get addresses_internal_id from
    Building._dangerously_save_forever(); this fills the rows that predate it,
    mirroring their addresses_id (a "clé d'interopérabilité BAN" array) as
    batid_address.internal_id values. Every cle in addresses_id is guaranteed
    to have a matching batid_address row: building_addresses_trigger (see
    specs/migration_lien_batiment_adresse.md) has enforced that through a
    foreign key on every write since migration 0081, and an address can never
    be deleted while still referenced (prevent_delete_linked_address_trigger).

    Each batch is written inside building_versioning_dangerously_disabled(), so
    this catch-up write does not flood batid_building_history with one row per
    building.

    Rows are walked in primary key order, one committed batch at a time, so the
    job can be interrupted and resumed. It only ever touches rows where
    addresses_internal_id IS NULL, so it never overwrites a value already
    written by the application and running it twice is harmless.

    Returns the number of buildings that received an addresses_internal_id.
    """
    updated = 0
    last_id = 0

    with connection.cursor() as cursor:
        # The worker connection carries a statement timeout of a few seconds,
        # which a batch of this size does not fit in.
        cursor.execute("SET statement_timeout = '0';")

        while True:
            # Take the batch bounds first, over every building regardless of
            # addresses_internal_id: a page made only of already filled or
            # address-less rows must still advance, or the loop never ends.
            cursor.execute(
                """
                SELECT max(id) FROM (
                    SELECT id FROM batid_building WHERE id > %s ORDER BY id LIMIT %s
                ) AS batch;
                """,
                [last_id, batch_size],
            )
            batch_max_id = cursor.fetchone()[0]

            if batch_max_id is None:
                break

            with transaction.atomic():
                with building_versioning_dangerously_disabled():
                    cursor.execute(
                        """
                        UPDATE batid_building b
                        SET addresses_internal_id = COALESCE(
                            (
                                SELECT array_agg(a.internal_id ORDER BY u.ord)
                                FROM unnest(b.addresses_id) WITH ORDINALITY AS u(cle, ord)
                                JOIN batid_address a ON a.id = u.cle
                            ),
                            '{}'
                        )
                        WHERE b.id > %s AND b.id <= %s
                          AND b.addresses_internal_id IS NULL
                          AND b.addresses_id IS NOT NULL;
                        """,
                        [last_id, batch_max_id],
                    )
                    updated += cursor.rowcount

            last_id = batch_max_id
            logger.info(
                "fill_building_addresses_internal_id: %s buildings filled, up to id %s",
                updated,
                last_id,
            )

    return updated
