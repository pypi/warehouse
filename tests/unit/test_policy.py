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

import os

import pretend

from warehouse import policy


def test_markdown_view(tmpdir):
    tmpdir = str(tmpdir)
    filename = "test.md"

    with open(os.path.join(tmpdir, filename), "w", encoding="utf8") as fp:
        fp.write("# This is my Test\n\nIt is a great test.\n")

    view = policy.markdown_view_factory(filename=filename)

    request = pretend.stub(registry=pretend.stub(settings={"policy.directory": tmpdir}))

    result = view(request)

    assert result == {
        "title": "This is my Test",
        "html": "<h1>This is my Test</h1>\n<p>It is a great test.</p>\n",
    }


def test_add_policy_view(monkeypatch):
    md_view = pretend.stub()
    markdown_view_factory = pretend.call_recorder(lambda filename: md_view)
    monkeypatch.setattr(policy, "markdown_view_factory", markdown_view_factory)

    config = pretend.stub(
        add_route=pretend.call_recorder(lambda *a, **kw: None),
        add_view=pretend.call_recorder(lambda *a, **kw: None),
    )

    policy.add_policy_view(config, "my-policy", "mine.md")

    assert config.add_route.calls == [
        pretend.call("policy.my-policy", "/policy/my-policy/")
    ]
    assert config.add_view.calls == [
        pretend.call(
            md_view,
            route_name="policy.my-policy",
            renderer="policy.html",
            has_translations=True,
        )
    ]
    assert markdown_view_factory.calls == [pretend.call(filename="mine.md")]


def test_includeme():
    config = pretend.stub(add_directive=pretend.call_recorder(lambda *a, **kw: None))

    policy.includeme(config)

    assert config.add_directive.calls == [
        pretend.call("add_policy", policy.add_policy_view, action_wrap=False)
    ]
