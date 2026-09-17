import logging

from django.db import connection

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10_000


def fill_address_internal_id(batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Give an internal_id to the addresses that predate migration 0146.

    Addresses created after that migration get their internal_id from the column
    DEFAULT; this fills the rows that already existed. Meant to be run once, from
    the fill_address_internal_id Celery task, before migration 0147, which makes
    internal_id unique and NOT NULL.

    Rows are walked in primary key order, one committed batch at a time, so the
    job can be interrupted and resumed. It only ever touches rows where
    internal_id IS NULL, so it never overwrites a value and running it twice is
    harmless.

    Returns the number of addresses that received an internal_id.
    """
    updated = 0
    # Lower bound of the next batch, exclusive. The empty string sorts before any
    # non empty interop key, whatever the collation.
    last_id = ""

    with connection.cursor() as cursor:
        # The worker connection carries a statement timeout of a few seconds,
        # which a batch of this size does not fit in.
        cursor.execute("SET statement_timeout = '0';")

        while True:
            # Take the batch bounds first: the UPDATE below cannot report them,
            # since a batch made only of already filled rows updates nothing.
            cursor.execute(
                """
                SELECT max(id) FROM (
                    SELECT id FROM batid_address WHERE id > %s ORDER BY id LIMIT %s
                ) AS batch;
                """,
                [last_id, batch_size],
            )
            batch_max_id = cursor.fetchone()[0]

            if batch_max_id is None:
                break

            # Range scan on the primary key index. Each statement is its own
            # transaction: the connection is in autocommit outside of a request.
            cursor.execute(
                """
                UPDATE batid_address
                SET internal_id = nextval('batid_address_internal_id_seq')
                WHERE id > %s AND id <= %s AND internal_id IS NULL;
                """,
                [last_id, batch_max_id],
            )

            updated += cursor.rowcount
            last_id = batch_max_id
            logger.info(
                "fill_address_internal_id: %s addresses filled, up to id %s",
                updated,
                last_id,
            )

    return updated
