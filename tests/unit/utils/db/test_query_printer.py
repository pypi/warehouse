# SPDX-License-Identifier: Apache-2.0

import logging

from sqlalchemy import select

from warehouse.packaging.models import Project
from warehouse.utils.db import query_printer


def test_print_query_renders_params(caplog):
    caplog.set_level(logging.DEBUG)

    query = select(Project.id, Project.name).where(Project.name == "value")
    assert "WHERE projects.name = :name_1" in str(query)

    query_printer.print_query(query)

    assert ":name_1" not in caplog.text
    assert "WHERE projects.name = 'value'" in caplog.text
