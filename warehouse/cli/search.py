# SPDX-License-Identifier: Apache-2.0

import click

from warehouse.cli import warehouse
from warehouse.search.tasks import prune_older_indices, reindex as _reindex


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
            h="health,status,index,id,pri,rep,docs.count,docs.deleted,store.size,creation.date.string",
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

    result = prune_older_indices(client, env_name)
    if result is None:
        click.echo(f"No alias found for {env_name}, aborting.", err=True)
        raise click.Abort

    click.echo(f"Current index: {result.current_index}")
    click.echo(f"Found {len(result.deleted)} older indices to delete.")
    for index in result.deleted:
        click.echo(f"Deleting index: {index}")
    click.echo("Done.")
