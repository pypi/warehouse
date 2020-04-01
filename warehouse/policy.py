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

import os.path

import html5lib
import jinja2
import mistune

import warehouse

DEFAULT_POLICY_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(warehouse.__file__)), "policies")
)


def markdown_view_factory(*, filename):
    def markdown_view(request):
        directory = request.registry.settings.get(
            "policy.directory", DEFAULT_POLICY_DIRECTORY
        )

        filepath = os.path.join(directory, filename)

        with open(filepath, "r", encoding="utf8") as fp:
            unrendered = fp.read()

        rendered = mistune.markdown(unrendered)
        html = html5lib.parse(rendered, namespaceHTMLElements=False, treebuilder="lxml")

        title = html.find("//h1[1]").text

        return {"title": title, "html": jinja2.Markup(rendered)}

    return markdown_view


def add_policy_view(config, name, filename):
    config.add_route("policy.{}".format(name), "/policy/{}/".format(name))
    config.add_view(
        markdown_view_factory(filename=filename),
        route_name="policy.{}".format(name),
        renderer="policy.html",
        has_translations=True,
    )


def includeme(config):
    config.add_directive("add_policy", add_policy_view, action_wrap=False)
