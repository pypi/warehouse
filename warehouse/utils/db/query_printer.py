# SPDX-License-Identifier: Apache-2.0

"""Logs the query with the parameters embedded into the query."""

import logging

from sqlalchemy.dialects import postgresql


def print_query(query) -> None:
    """
    Prints the query with the parameters embedded into the query.

    Useful for development/debugging purposes.
    """
    logging.debug(
        str(
            query.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
    )
