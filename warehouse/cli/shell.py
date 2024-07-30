# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
