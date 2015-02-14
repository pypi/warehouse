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

from warehouse.config import configure


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--config", "-c",
    multiple=True,
    type=click.Path(resolve_path=True),
)
@click.pass_context
def warehouse(ctx, config):
    settings = {}

    if config:
        settings["yml.location"] = config

    ctx.obj = configure(settings=settings)


# We want to automatically import all of the warehouse.cli.* modules so that
# any commands registered in any of them will be discovered.
for _, name, _ in pkgutil.walk_packages(__path__):
    importlib.import_module("." + name, package=__name__)
