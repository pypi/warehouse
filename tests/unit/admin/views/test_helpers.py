# SPDX-License-Identifier: Apache-2.0

import pytest

from psycopg import OperationalError
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy import func, select, text

from warehouse.admin.views.helpers import estimate_row_count, execute_bounded

from ....common.db.packaging import JournalEntryFactory


class TestEstimateRowCount:
    def test_never_negative(self, db_request):
        """reltuples is -1 until first ANALYZE; estimates clamp to zero."""
        assert estimate_row_count(db_request, ["journals"]) >= 0

    def test_reflects_analyzed_rows(self, db_request):
        JournalEntryFactory.create_batch(7)
        db_request.db.execute(text("ANALYZE journals"))

        assert estimate_row_count(db_request, ["journals"]) == 7

    def test_sums_multiple_tables(self, db_request):
        # Each journal entry's submitted_by SubFactory also creates a user.
        JournalEntryFactory.create_batch(7)
        db_request.db.execute(text("ANALYZE journals"))
        db_request.db.execute(text("ANALYZE users"))

        assert estimate_row_count(db_request, ["journals", "users"]) == 14

    def test_unknown_table_is_zero(self, db_request):
        assert estimate_row_count(db_request, ["no_such_table"]) == 0


class TestExecuteBounded:
    def test_cancelled_query_becomes_bad_request(self, db_request):
        """A query cancelled by the statement timeout surfaces as a 400."""
        with pytest.raises(HTTPBadRequest):
            execute_bounded(db_request, select(func.pg_sleep(1)), timeout_ms=10)

    def test_other_database_errors_propagate(self, db_request, mocker):
        """Only cancelled queries become a 400; real outages surface.

        warehouse.db re-raises the raw psycopg exception engine-wide, so
        that is what execute_bounded sees.
        """
        mocker.patch.object(
            db_request.db,
            "execute",
            autospec=True,
            side_effect=OperationalError("server closed the connection"),
        )

        with pytest.raises(OperationalError):
            execute_bounded(db_request, select(func.now()), timeout_ms=10_000)
