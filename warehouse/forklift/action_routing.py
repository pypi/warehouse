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


def add_legacy_action_route(config, name, action, **kwargs):
    config.add_route(name, "/legacy/", pypi_action=action, **kwargs)


def includeme(config):
    config.add_directive(
        "add_legacy_action_route", add_legacy_action_route, action_wrap=False
    )
