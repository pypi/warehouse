# SPDX-License-Identifier: Apache-2.0

import click

from opensearchpy.exceptions import NotFoundError

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


@search.command()
@click.pass_obj
def print_indices(config):
    """
    Print details about all search existing indices.
    """
    client = config.registry["opensearch.client"]
    # CAT Client https://docs.opensearch.org/latest/api-reference/cat/index/
    # https://opensearch-project.github.io/opensearch-py/api-ref/clients/cat_client.html
    click.echo(
        client.cat.indices(
            index="production*,staging*",
            h="health,status,index,id,pri,rep,docs.count,docs.deleted,store.size,creation.date.string",  # noqa: E501
            s="creation.date.string:desc",
            v=True,  # include column headers for easier reading
        )
    )

    aliases = client.indices.get_alias(index="production*,staging*")
    click.echo("\nCurrent Aliases:")
    for index, alias in aliases.items():
        for a in alias["aliases"]:
            click.echo(f"{a} -> {index}")


@search.command()
@click.argument("env_name", type=click.Choice(["production", "staging", "development"]))
@click.pass_obj
def delete_older_indices(config, env_name):
    """
    Delete older search indices, keeping the latest two.
    Ensure the current alias is pointing to the latest index before running this.

    ENV_NAME: Environment name (e.g., 'production' or 'staging')
    """
    client = config.registry["opensearch.client"]

    # Gets alias of current "live" index, don't remove that one
    try:
        alias = client.indices.get_alias(name=env_name)
    except NotFoundError:
        click.echo(f"No alias found for {env_name}, aborting.", err=True)
        raise click.Abort()

    current_index = list(alias.keys())[0]
    click.echo(f"Current index: {current_index}")

    indices = client.indices.get(index=f"{env_name}-*")
    # sort the response by date, keep most recent 2
    indices = sorted(indices.keys(), reverse=True)
    # remove current index from the list
    indices.remove(current_index)
    # Remove the most recent, non-alias one from the list
    if indices:
        indices.pop(0)
    # Remaining indices are older than the most recent two, delete them
    click.echo(f"Found {len(indices)} older indices to delete.")

    for index in indices:
        click.echo(f"Deleting index: {index}")
        client.indices.delete(index=index)

    click.echo("Done.")
