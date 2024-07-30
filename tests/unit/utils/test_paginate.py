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


class FakeSuggestion:
    def __init__(self, options):
        self.options = options


class FakeSuggest:
    def __init__(self, name_suggestion):
        self.name_suggestion = name_suggestion


class FakeResult:
    def __init__(self, data, total):
        self.data = data
        self.total = total

    @property
    def hits(self):
        return pretend.stub(total={"value": self.total})

    def __iter__(self):
        yield from self.data


class FakeResult6:
    def __init__(self, data, total):
        self.data = data
        self.total = total

    @property
    def hits(self):
        return pretend.stub(total=self.total)

    def __iter__(self):
        yield from self.data


class FakeSuggestResult(FakeResult):
    def __init__(self, data, total, options=None, suggestion=None):
        super().__init__(data, total)
        self.options = options
        self.suggestion = suggestion

    @property
    def suggest(self):
        if self.suggestion is None:
            suggestion = FakeSuggestion(options=self.options)
            return FakeSuggest(name_suggestion=[suggestion])
        return FakeSuggest(name_suggestion=self.suggestion)


class FakeQuery:
    def __init__(self, fake):
        self.fake = fake
        self.range = slice(None)

    def __getitem__(self, range):
        self.range = range
        return self

    def execute(self):
        return FakeResult(self.fake[self.range], len(self.fake))


class FakeQuery6:
    def __init__(self, fake):
        self.fake = fake
        self.range = slice(None)

    def __getitem__(self, range):
        self.range = range
        return self

    def execute(self):
        return FakeResult6(self.fake[self.range], len(self.fake))


class FakeSuggestQuery(FakeQuery):
    def __init__(self, fake, options=None, suggestion=None):
        super().__init__(fake)
        self.options = options
        self.suggestion = suggestion

    def execute(self):
        data = self.fake[self.range]
        total = len(self.fake)
        return FakeSuggestResult(data, total, self.options, self.suggestion)


class TestOpenSearchWrapper:
    def test_slices_and_length(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        assert wrapper[1:3] == [2, 3]
        assert len(wrapper) == 6

    def test_slice_start_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[6:10] == []
        assert len(wrapper) == 5

    def test_slice_end_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[1:10] == [2, 3, 4, 5]
        assert len(wrapper) == 5

    def test_second_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))
        wrapper[1:3]

        with pytest.raises(RuntimeError):
            wrapper[1:3]

    def test_len_before_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery([1, 2, 3, 4, 5, 6]))

        with pytest.raises(RuntimeError):
            len(wrapper)

    def test_best_guess_suggestion(self):
        fake_option = pretend.stub()
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[fake_option])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess == fake_option

    def test_best_guess_suggestion_no_suggestions(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], suggestion=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None

    def test_best_guess_suggestion_no_options(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None


class TestOpenSearchWrapper6:
    def test_slices_and_length(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        assert wrapper[1:3] == [2, 3]
        assert len(wrapper) == 6

    def test_slice_start_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[6:10] == []
        assert len(wrapper) == 5

    def test_slice_end_clamps_to_max(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper.max_results = 5
        assert wrapper[1:10] == [2, 3, 4, 5]
        assert len(wrapper) == 5

    def test_second_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))
        wrapper[1:3]

        with pytest.raises(RuntimeError):
            wrapper[1:3]

    def test_len_before_slice_fails(self):
        wrapper = paginate._OpenSearchWrapper(FakeQuery6([1, 2, 3, 4, 5, 6]))

        with pytest.raises(RuntimeError):
            len(wrapper)

    def test_best_guess_suggestion(self):
        fake_option = pretend.stub()
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[fake_option])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess == fake_option

    def test_best_guess_suggestion_no_suggestions(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], suggestion=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None

    def test_best_guess_suggestion_no_options(self):
        query = FakeSuggestQuery([1, 2, 3, 4, 5, 6], options=[])
        wrapper = paginate._OpenSearchWrapper(query)
        wrapper[1:3]

        assert wrapper.best_guess is None


def test_opensearch_page_has_wrapper(monkeypatch):
    page_obj = pretend.stub()
    page_cls = pretend.call_recorder(lambda *a, **kw: page_obj)
    monkeypatch.setattr(paginate, "Page", page_cls)

    assert paginate.OpenSearchPage("first", second="foo") is page_obj
    assert page_cls.calls == [
        pretend.call("first", second="foo", wrapper_class=paginate._OpenSearchWrapper)
    ]


def test_paginate_url(pyramid_request):
    pyramid_request.GET = MultiDict(pyramid_request.GET)
    pyramid_request.GET["foo"] = "bar"

    url = pretend.stub()
    pyramid_request.current_route_path = pretend.call_recorder(lambda _query: url)

    url_maker = paginate.paginate_url_factory(pyramid_request)

    assert url_maker(5) is url
    assert pyramid_request.current_route_path.calls == [
        pretend.call(_query=[("foo", "bar"), ("page", 5)])
    ]
