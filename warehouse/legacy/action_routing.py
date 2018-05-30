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


def pypi_action(action):
    def predicate(info, request):
        return action == request.params.get(":action", None)

    return predicate


def add_pypi_action_route(config, name, action, **kwargs):
    custom_predicates = kwargs.pop("custom_predicates", [])
    custom_predicates += [pypi_action(action)]

    config.add_route(name, "/pypi", custom_predicates=custom_predicates, **kwargs)


def add_pypi_action_redirect(config, action, target, **kwargs):
    custom_predicates = kwargs.pop("custom_predicates", [])
    custom_predicates += [pypi_action(action)]

    config.add_redirect("/pypi", target, custom_predicates=custom_predicates, **kwargs)


def includeme(config):
    config.add_directive(
        "add_pypi_action_route", add_pypi_action_route, action_wrap=False
    )
    config.add_directive(
        "add_pypi_action_redirect", add_pypi_action_redirect, action_wrap=False
    )
