# SPDX-License-Identifier: Apache-2.0

import click
import pyramid.scripting
import transaction

from warehouse.cli import warehouse


def autodetect():
    try:
        import bpython  # noqa: F401  # pyright: ignore[reportMissingImports]

        return "bpython"
    except ImportError:
        try:
            import IPython  # noqa: F401  # pyright: ignore[reportMissingImports]

            return "ipython"
        except ImportError:
            pass

    return "plain"


def bpython(**locals_):
    import bpython  # pyright: ignore[reportMissingImports]

    bpython.embed(locals_)


def ipython(**locals_):
    from IPython import start_ipython  # pyright: ignore[reportMissingImports]

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

    Test factories are automatically configured to use the shell's database session.
    Import and use them like:
        from tests.common.db.accounts import UserFactory
        user = UserFactory.create(username="testuser")
    """

    # Lazy import; this is the only thing we need before picking a Session.
    from warehouse.config import Environment

    is_dev = config.registry.settings.get("warehouse.env") == Environment.development

    # In dev, use the scoped_session from `tests.common.db` that
    # WarehouseFactory points at as its `sqlalchemy_session`. Calling it with
    # `bind=` registers the resulting Session in the thread-local registry,
    # so `UserFactory.create(...)` and `request.db` end up sharing one
    # Session (same identity map, same transaction).
    #
    # Anywhere else, fall back to the bare `warehouse.db.Session` sessionmaker
    # so we don't pull test code into a prod shell. The shell is still useful
    # in prod for incident debugging; the factory wiring is the dev-only part.
    # Importing a factory in a prod shell will fail because `factory_boy`
    # isn't installed there, which is the right signal.
    if is_dev:
        from tests.common.db import Session
    else:
        from warehouse.db import Session

    if type_ is None:
        type_ = autodetect()

    runner = {"bpython": bpython, "ipython": ipython, "plain": plain}[type_]

    env = pyramid.scripting.prepare(registry=config.registry)
    request = env["request"]
    env["request"].tm = transaction.TransactionManager(explicit=True)

    session = Session(bind=config.registry["sqlalchemy.engine"])
    request.db = session

    try:
        runner(config=config, db=session, request=request)
    except ImportError:
        raise click.ClickException(f"The {type_!r} shell is not available.") from None
