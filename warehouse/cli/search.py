# SPDX-License-Identifier: Apache-2.0

import click

from warehouse.cli import warehouse
from warehouse.search.tasks import reindex as _reindex


@warehouse.group()
def search():
    """
    Manage the Warehouse Search.
    """


@search.command()
@click.pass_obj
def reindex(config):
    """
    Recreate the Search Index.
    """

    request = config.task(_reindex).get_request()
    config.task(_reindex).run(request)
