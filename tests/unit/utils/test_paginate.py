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

import pretend
import pytest

from webob.multidict import MultiDict

from warehouse.utils import paginate


class FakeResult:

    def __init__(self, data, total):
        self.data = data
        self.total = total

    @property
    def hits(self):
        return pretend.stub(total=self.total)

    def __iter__(self):
        for i in self.data:
            yield i


class FakeQuery:

    def __init__(self, fake):
        self.fake = fake
        self.range = slice(None)

    def __getitem__(self, range):
        self.range = range
        return self

    @property
    def results(self):
        return pretend.stub(hits=pretend.stub(total=len(self.fake)))

    def execute(self):
        return FakeResult(self.fake[self.range], len(self.fake))


class TestElasticsearchWrapper:

    def test_slices_and_length(self):
        wrapper = paginate._ElasticsearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        assert wrapper[1:3] == [2, 3]
        assert len(wrapper) == 6

    def test_second_slice_fails(self):
        wrapper = paginate._ElasticsearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper[1:3]

        with pytest.raises(RuntimeError):
            wrapper[1:3]

    def test_len_before_slice_fails(self):
        wrapper = paginate._ElasticsearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))

        with pytest.raises(RuntimeError):
            len(wrapper)


def test_elasticsearch_page_has_wrapper(monkeypatch):
    page_obj = pretend.stub()
    page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
    monkeypatch.setattr(paginate, "Page", page_cls)

    assert paginate.ElasticsearchPage("first", second="foo") is page_obj
    assert page_cls.calls == [
        pretend.call(
            "first",
            second="foo",
            wrapper_class=paginate._ElasticsearchWrapper,
        ),
    ]


def test_paginate_url(pyramid_request):
    pyramid_request.GET = MultiDict(pyramid_request.GET)
    pyramid_request.GET["foo"] = "bar"

    url = pretend.stub()
    pyramid_request.current_route_path = \
        pretend.call_recorder(lambda _query: url)

    url_maker = paginate.paginate_url_factory(pyramid_request)

    assert url_maker(5) is url
    assert pyramid_request.current_route_path.calls == [
        pretend.call(_query=[("foo", "bar"), ("page", 5)]),
    ]
