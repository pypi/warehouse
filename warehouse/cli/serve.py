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

import multiprocessing

import click

try:  # pragma: no cover
    from gunicorn.app.base import BaseApplication
    HAS_GUNICORN = True
except ImportError:
    class BaseApplication:
        pass
    HAS_GUNICORN = False

from warehouse.cli import warehouse


class Application(BaseApplication):

    def __init__(self, app, *args, options, **kwargs):
        self.options = options
        self.application = app

        super().__init__(*args, **kwargs)

    def load_config(self):
        config = {
            key: value for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


@warehouse.command()
@click.option("-b", "--bind", metavar="ADDRESS", help="The socket to bind.")
@click.option(
    "--reload/--no-reload", "reload_",
    help="Restart workers when code changes."
)
@click.pass_obj
def serve(config, bind, reload_):
    """
    Serve Warehouse using gunicorn.

    Note: Requires installing with the serve extra.
    """

    if not HAS_GUNICORN:
        raise click.ClickException(
            "Cannot use 'warehouse serve' without gunicorn installed."
        )

    options = {
        "bind": bind,
        "reload": reload_,
        # The gunicorn docs recommend (2 x $num_cores) + 1
        "workers": (2 * multiprocessing.cpu_count()) + 1,
        "proc_name": "warehouse",
    }

    Application(config.make_wsgi_app(), options=options).run()
