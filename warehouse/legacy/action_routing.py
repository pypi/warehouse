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


class PyPIActionPredicate:
    def __init__(self, action: str, info):
        self.action_name = action

    def text(self) -> str:
        return f"pypi_action = {self.action_name}"

    phash = text

    def __call__(self, context, request) -> bool:
        return self.action_name == request.params.get(":action", None)


def add_pypi_action_route(config, name, action, **kwargs):
    config.add_route(name, "/pypi", pypi_action=action, **kwargs)


def add_pypi_action_redirect(config, action, target, **kwargs):
    config.add_redirect("/pypi", target, pypi_action=action, **kwargs)


def includeme(config):
    config.add_route_predicate("pypi_action", PyPIActionPredicate)
    config.add_directive(
        "add_pypi_action_route", add_pypi_action_route, action_wrap=False
    )
    config.add_directive(
        "add_pypi_action_redirect", add_pypi_action_redirect, action_wrap=False
    )
