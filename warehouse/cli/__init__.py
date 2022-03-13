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
