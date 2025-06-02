# SPDX-License-Identifier: Apache-2.0

import importlib
import pkgutil

import click


class LazyConfig:
    # This is defined here instead of anywhere else because we want to limit
    # the modules that this imports from Warehouse. Anything imported in
    # warehouse/__init__.py or warehouse/cli/__init__.py will not be able to
    # be reloaded by ``warehouse serve --reload``.

    def __init__(self, *args, **kwargs):
        self.__args = args
        self.__kwargs = kwargs
        self.__config = None

    def __getattr__(self, name):
        if self.__config is None:
            from warehouse.config import configure

            self.__config = configure(*self.__args, **self.__kwargs)
        return getattr(self.__config, name)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
def warehouse(ctx):
    ctx.obj = LazyConfig()


# We want to automatically import all of the warehouse.cli.* modules so that
# any commands registered in any of them will be discovered.
for _, name, _ in pkgutil.walk_packages(__path__, prefix=__name__ + "."):  # type: ignore # noqa
    importlib.import_module(name)
