# SPDX-License-Identifier: Apache-2.0

"""Logs the query with the parameters embedded into the query."""

import structlog

from sqlalchemy.dialects import postgresql

logger = structlog.get_logger(__name__)


def print_query(query) -> None:
    """
    Prints the query with the parameters embedded into the query.

    Useful for development/debugging purposes.
    """
    logger.debug(
        str(
            query.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
    )
