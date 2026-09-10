# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import select

from warehouse.packaging.models import Project
from warehouse.utils.db import query_printer


def test_print_query_renders_params(mocker):
    """
    Asserted via a patched logger rather than structlog.testing.capture_logs:
    once the functional tests have run the app's structlog.configure (with
    cache_logger_on_first_use), capture_logs can no longer intercept this
    module-level logger.
    """
    log = mocker.patch.object(query_printer, "logger")

    query = select(Project.id, Project.name).where(Project.name == "value")
    assert "WHERE projects.name = :name_1" in str(query)

    query_printer.print_query(query)

    (compiled,) = log.debug.call_args.args
    assert ":name_1" not in compiled
    assert "WHERE projects.name = 'value'" in compiled
