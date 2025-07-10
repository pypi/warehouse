# SPDX-License-Identifier: Apache-2.0

import click

from warehouse.cli import warehouse


def autodetect():
    try:
        import bpython  # noqa

        return "bpython"
    except ImportError:
        try:
            import IPython  # noqa

            return "ipython"
        except ImportError:
            pass

    return "plain"


def bpython(**locals_):
    import bpython

    bpython.embed(locals_)


def ipython(**locals_):
    from IPython import start_ipython

    start_ipython(argv=[], user_ns=locals_)


def plain(**locals_):
    import code

    code.interact(local=locals_)


@warehouse.command()
@click.option(
    "--type",
    "type_",
    type=click.Choice(["bpython", "ipython", "plain"]),
    help="What type of shell to use, default will autodetect.",
)
@click.pass_obj
def shell(config, type_):
    """
    Open up a Python shell with Warehouse preconfigured in it.
    """

    # Imported here because we don't want to trigger an import from anything
    # but warehouse.cli at the module scope.
    from warehouse.db import Session

    if type_ is None:
        type_ = autodetect()

    runner = {"bpython": bpython, "ipython": ipython, "plain": plain}[type_]

    session = Session(bind=config.registry["sqlalchemy.engine"])

    try:
        runner(config=config, db=session)
    except ImportError:
        raise click.ClickException(f"The {type_!r} shell is not available.") from None
